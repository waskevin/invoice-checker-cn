from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
import os
import threading
import time
import uuid

import fitz
from openpyxl import load_workbook

from invoice_checker.exporter import export_invoices
from invoice_checker.models import Invoice, InvoiceKind, InvoiceStatus
from invoice_checker.extraction import PdfExtraction
from invoice_checker.parsers import ChineseVatInvoiceParser
from invoice_checker.shell_integration import import_shell_selection
from invoice_checker.services import InvoiceService
from invoice_checker.storage import InvoiceRepository


TARGET = "示例购买方有限公司"
TARGET_TAX_ID = "91310000000000000X"


def cjk_font_file() -> str:
    env_font = os.environ.get("INVOICE_CHECKER_TEST_FONT")
    candidates = [
        Path(env_font) if env_font else None,
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simkai.ttf"),
        Path("C:/Windows/Fonts/Deng.ttf"),
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return str(candidate)
    raise FileNotFoundError("No CJK font found for generating test PDFs.")


def test_hotkey_setting_is_normalized_and_rejects_invalid_combinations(tmp_path: Path) -> None:
    """The captured shortcut must be persisted in the exact format used by the helper."""
    from invoice_checker.hotkey import parse_hotkey

    assert parse_hotkey("control + alt + r").display == "Ctrl+Alt+R"
    assert parse_hotkey("Alt+F8").display == "Alt+F8"

    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)
    service.set_hotkey("control + alt + r")
    assert service.hotkey == "Ctrl+Alt+R"
    assert InvoiceRepository(tmp_path / "invoices.sqlite3").get_hotkey() == "Ctrl+Alt+R"

    import pytest
    with pytest.raises(ValueError, match="快捷键"):
        parse_hotkey("R")


def test_command_line_separates_hidden_hotkey_mode_from_pdf_imports() -> None:
    from invoice_checker.__main__ import parse_command_line

    helper = parse_command_line(["--hotkey-helper"])
    normal = parse_command_line(["one.pdf", "two.pdf"])

    assert helper.hotkey_helper is True
    assert normal.hotkey_helper is False
    assert normal.pdf_files == [Path("one.pdf"), Path("two.pdf")]


def test_single_instance_payload_round_trips_forwarded_pdf_paths(tmp_path: Path) -> None:
    from invoice_checker.single_instance import decode_paths, encode_paths

    first = tmp_path / "发票 1.pdf"
    second = tmp_path / "invoice_2.pdf"

    assert decode_paths(encode_paths([first, second])) == [first, second]


def test_single_instance_forwards_paths_to_existing_listener(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtNetwork import QLocalServer
    from invoice_checker.single_instance import SingleInstance

    app = QApplication.instance() or QApplication([])
    server_name = f"invoice-checker-test-{uuid.uuid4()}"
    pdf = tmp_path / "forwarded.pdf"
    received: list[list[Path]] = []
    primary = SingleInstance(server_name)
    server = primary.listen(received.append)
    sent: list[bool] = []
    try:
        sender = threading.Thread(target=lambda: sent.append(SingleInstance(server_name).send_to_existing([pdf], 3000)))
        sender.start()
        deadline = time.time() + 5
        while not received and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        sender.join(timeout=2)
        app.processEvents()
        assert sent == [True]
        assert received == [[pdf]]
    finally:
        server.close()
        QLocalServer.removeServer(server_name)


def test_hotkey_log_records_the_selected_paths(tmp_path: Path) -> None:
    from invoice_checker.hotkey_helper import append_hotkey_log

    log = tmp_path / "hotkey.log"
    append_hotkey_log("检测到 PDF：demo.pdf", log)

    assert "检测到 PDF：demo.pdf" in log.read_text(encoding="utf-8")


def test_shell_output_prefers_existing_pdf_paths(tmp_path: Path) -> None:
    from invoice_checker.hotkey_helper import pdf_paths_from_shell_output

    pdf = tmp_path / "selected.pdf"
    pdf.touch()
    output = '["' + str(pdf).replace("\\", "\\\\") + '", "not-a-pdf.txt"]'

    assert pdf_paths_from_shell_output(output) == [str(pdf)]


def test_hotkey_falls_back_to_clipboard_pdf_paths_when_shell_selection_is_empty(tmp_path: Path) -> None:
    from invoice_checker.hotkey_helper import selected_or_clipboard_pdf_paths

    pdf = tmp_path / "clipboard.pdf"
    pdf.touch()

    assert selected_or_clipboard_pdf_paths(lambda: [], lambda: [str(pdf)]) == [str(pdf)]


def test_hotkey_does_not_read_clipboard_when_shell_selection_has_pdfs(tmp_path: Path) -> None:
    from invoice_checker.hotkey_helper import selected_or_clipboard_pdf_paths

    selected = tmp_path / "selected.pdf"
    selected.touch()
    clipboard = tmp_path / "clipboard.pdf"
    clipboard.touch()

    assert selected_or_clipboard_pdf_paths(lambda: [str(selected)], lambda: [str(clipboard)]) == [str(selected)]


def make_invoice_pdf(path: Path, *, buyer: str = TARGET, number: str = "123456789012", total: str = "1130.00", kind: str = "普通发票") -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_font(fontname="cjk", fontfile=cjk_font_file())
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                f"电子发票（{kind}）",
                f"发票号码：{number}",
                "开票日期：2026年09月20日",
                "购买方信息",
                f"名称：{buyer}",
                "销售方信息",
                "名称：深圳示例销售有限公司",
                f"价税合计（小写）¥{total}",
            ]
        ),
        fontsize=12,
        fontname="cjk",
    )
    document.save(path)
    document.close()


def test_parses_required_fields_from_text_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "normal.pdf"
    make_invoice_pdf(pdf)

    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)
    invoice = service.process_file(pdf)

    assert invoice.number == "123456789012"
    assert invoice.invoice_kind is InvoiceKind.ORDINARY
    assert invoice.issue_date.isoformat() == "2026-09-20"
    assert invoice.buyer_name == TARGET
    assert invoice.seller_name == "深圳示例销售有限公司"
    assert invoice.total_with_tax == Decimal("1130.00")
    assert invoice.status is InvoiceStatus.VALID
    assert invoice.file_path.name == "示例购买方有限公司_深圳示例销售有限公司_2026-09-20_普票_1130.00.pdf"
    assert invoice.file_path.exists()
    assert not pdf.exists()


def test_rename_uses_sequence_when_target_name_exists(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    make_invoice_pdf(first, number="RENAME-01", total="10.00")
    make_invoice_pdf(second, number="RENAME-02", total="10.00")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)

    service.process_file(first)
    renamed = service.process_file(second)

    assert renamed.file_path.name == "示例购买方有限公司_深圳示例销售有限公司_2026-09-20_普票_10.00_2.pdf"


def test_parses_telecom_special_invoice_with_split_party_and_total_labels() -> None:
    extracted = PdfExtraction(
        text="""电子发票（增值税专用发票） 发票号码：26957000000239743562
开票日期：2026年09月06日
购                                   销
买 名称：示例购买方有限公司                售 名称：中国电信股份有限公司深圳分公司
方                                   方
信 统一社会信用代码/纳税人识别号：91310000000000000X  信 统一社会信用代码/纳税人识别号：91440300748856239Q
息                                   息
价税合计（大写） 壹拾叁圆玖角 （小写）¥13.90""",
        words=(),
    )

    fields = ChineseVatInvoiceParser().parse(extracted)

    assert fields["invoice_kind"] is InvoiceKind.SPECIAL
    assert fields["buyer_name"] == "示例购买方有限公司"
    assert fields["seller_name"] == "中国电信股份有限公司深圳分公司"
    assert fields["total_with_tax"] == Decimal("13.90")


def test_parses_party_names_from_coordinate_columns_when_vertical_labels_are_split() -> None:
    extracted = PdfExtraction(
        text="电子发票(增值税专用发票)\n发票号码:\n25447000000895954202\n开票日期:\n2025年08月08日\n(小写)\n¥546.50",
        words=(
            (41, 93, 50, 104, "名"), (55, 91, 70, 109, "称:"),
            (74, 95, 178, 104, "示例购买方有限公司"),
            (326, 93, 335, 104, "名"), (340, 90, 355, 108, "称:"),
            (356, 95, 436, 104, "广州晶东贸易有限公司"),
        ),
    )

    fields = ChineseVatInvoiceParser().parse(extracted)

    assert fields["buyer_name"] == "示例购买方有限公司"
    assert fields["seller_name"] == "广州晶东贸易有限公司"


def test_parses_buyer_tax_id_from_labeled_left_column_instead_of_invoice_number() -> None:
    extracted = PdfExtraction(
        text="""电子发票（增值税专用发票）
发票号码：25337000000550711150
开票日期：2025年11月20日
购
买
方
信
息
名称：示例购买方有限公司
销
售
方
信
息
名称：阿里云计算有限公司
（小写）¥149.35""",
        words=(
            (491, 32, 581, 41, "25337000000550711150"),
            (31, 105, 175, 114, "名称：示例购买方有限公司"),
            (316, 105, 424, 114, "名称：阿里云计算有限公司"),
            (31, 116, 296, 128, "统一社会信用代码/纳税人识别号:91310000000000000X"),
            (316, 116, 581, 128, "统一社会信用代码/纳税人识别号:91330106673959654P"),
        ),
    )

    fields = ChineseVatInvoiceParser().parse(extracted)

    assert fields["number"] == "25337000000550711150"
    assert fields["buyer_tax_id"] == "91310000000000000X"


def test_target_buyer_setting_persists_in_sqlite(tmp_path: Path) -> None:
    database = tmp_path / "invoices.sqlite3"
    repository = InvoiceRepository(database)

    assert repository.get_target_buyer("示例购买方有限公司") == "示例购买方有限公司"
    repository.set_target_buyer("测试公司")

    assert InvoiceRepository(database).get_target_buyer("默认公司") == "测试公司"


def test_reimport_replaces_a_previous_parse_failure_for_same_file(tmp_path: Path) -> None:
    pdf = tmp_path / "retry.pdf"
    make_invoice_pdf(pdf, number="RETRY-01", total="1.00")
    repository = InvoiceRepository(tmp_path / "invoices.sqlite3")
    repository.add(Invoice(file_path=pdf, sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                           status=InvoiceStatus.PARSE_ERROR, status_message="旧版解析失败"))

    invoice = InvoiceService(repository, TARGET).process_file(pdf)

    assert invoice.status is InvoiceStatus.VALID
    assert len(repository.list_all()) == 1


def test_gui_amounts_are_copyable_plain_numbers(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from invoice_checker.gui import MainWindow

    pdf = tmp_path / "amount.pdf"
    make_invoice_pdf(pdf, total="1130.00")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)
    service.process_file(pdf)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(service)

    amount_column = window.headers.index("价税合计")
    assert window.table.item(0, amount_column).text() == "1130.00"
    assert window.total_input.text() == "1130.00"
    window.copy_cell(0, amount_column)
    assert QApplication.clipboard().text() == "1130.00"
    window.copy_cell(0, 0)
    assert QApplication.clipboard().text() == "amount.pdf"


def test_gui_displays_and_copies_full_invoice_file_path(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from invoice_checker.gui import MainWindow

    pdf = tmp_path / "path-copy.pdf"
    make_invoice_pdf(pdf)
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)
    service.process_file(pdf)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(service)
    path_column = window.headers.index("文件路径")

    assert window.table.item(0, path_column).text() == str(pdf.resolve())
    opened: list[Path] = []
    window.open_file_location = opened.append  # type: ignore[method-assign]
    window.copy_cell(0, path_column)
    assert opened == [pdf.resolve()]


def test_gui_promotes_clipboard_then_hotkey_workflow(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from invoice_checker.gui import MainWindow

    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(service)

    assert "Ctrl+C" in window.drop_hint.text()
    assert service.hotkey in window.drop_hint.text()
    assert "剪贴板" in window.hotkey_status_label.text()


def test_hotkey_ready_message_promotes_clipboard_workflow() -> None:
    from invoice_checker.hotkey_helper import hotkey_ready_message
    from invoice_checker.hotkey import parse_hotkey

    message = hotkey_ready_message(parse_hotkey("Alt+R"))

    assert "Ctrl+C" in message
    assert "Alt+R" in message
    assert "剪贴板" in message


def test_remove_selected_imports_keeps_original_pdf_and_updates_summary(tmp_path: Path) -> None:
    pdf = tmp_path / "remove-me.pdf"
    make_invoice_pdf(pdf, total="50.00")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)
    imported = service.process_file(pdf)

    assert service.remove_files([imported.file_path]) == 1

    assert pdf.exists()
    assert service.list_invoices() == []
    assert service.summary().valid_total == Decimal("0.00")


def test_gui_remove_selection_refreshes_visible_total(tmp_path: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from invoice_checker.gui import MainWindow

    pdf = tmp_path / "gui-remove.pdf"
    make_invoice_pdf(pdf, total="50.00")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)
    service.process_file(pdf)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(service)
    window.table.selectRow(0)

    window.remove_selected_rows()

    assert window.table.rowCount() == 0
    assert window.total_input.text() == "0.00"
    assert pdf.exists()


def test_shell_selection_imports_batch_and_returns_copyable_batch_total(tmp_path: Path) -> None:
    first = tmp_path / "shell-1.pdf"
    second = tmp_path / "shell-2.pdf"
    make_invoice_pdf(first, number="SHELL-01", total="10.00")
    make_invoice_pdf(second, number="SHELL-02", total="20.50")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)

    batch = import_shell_selection(service, [first, second])

    assert len(batch.invoices) == 2
    assert batch.clipboard_total == "30.50"


def test_shell_selection_refuses_total_when_buyers_differ(tmp_path: Path) -> None:
    first = tmp_path / "same-buyer.pdf"
    second = tmp_path / "different-buyer.pdf"
    make_invoice_pdf(first, number="BUYER-01", total="10.00")
    make_invoice_pdf(second, buyer="其他有限公司", number="BUYER-02", total="20.00")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET, auto_rename=False)

    batch = import_shell_selection(service, [first, second])

    assert batch.clipboard_total is None
    assert "购买方不一致" in batch.copy_block_reason


def test_wrong_buyer_is_warning_and_excluded_from_total(tmp_path: Path) -> None:
    pdf = tmp_path / "wrong-buyer.pdf"
    make_invoice_pdf(pdf, buyer="其他有限公司")

    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)
    invoice = service.process_file(pdf)

    assert invoice.status is InvoiceStatus.BUYER_MISMATCH
    assert service.summary().valid_total == Decimal("0.00")


def test_missing_or_wrong_buyer_tax_id_is_not_a_valid_invoice() -> None:
    from datetime import date
    from invoice_checker.validation import validate_invoice

    missing_tax_id = Invoice(Path("missing-tax.pdf"), "sha", number="TAX-01", issue_date=date(2026, 1, 1),
                             buyer_name=TARGET, buyer_tax_id=None, total_with_tax=Decimal("10.00"))
    wrong_tax_id = Invoice(Path("wrong-tax.pdf"), "sha2", number="TAX-02", issue_date=date(2026, 1, 1),
                           buyer_name=TARGET, buyer_tax_id="914400000000000000", total_with_tax=Decimal("10.00"))

    validate_invoice(missing_tax_id, TARGET, TARGET_TAX_ID)
    validate_invoice(wrong_tax_id, TARGET, TARGET_TAX_ID)

    assert missing_tax_id.status is InvoiceStatus.BUYER_MISMATCH
    assert "税号" in missing_tax_id.status_message
    assert wrong_tax_id.status is InvoiceStatus.BUYER_MISMATCH
    assert "914400000000000000" in wrong_tax_id.status_message


def test_number_or_sha_duplicate_is_excluded_from_total(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    make_invoice_pdf(first, number="DUPLICATE-01", total="88.00")
    make_invoice_pdf(second, number="DUPLICATE-01", total="88.00")

    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)
    original = service.process_file(first)
    duplicate = service.process_file(second)

    assert original.status is InvoiceStatus.VALID
    assert duplicate.status is InvoiceStatus.DUPLICATE
    assert service.summary().valid_count == 1
    assert service.summary().valid_total == Decimal("88.00")


def test_sha_duplicate_detects_identical_content_with_different_names(tmp_path: Path) -> None:
    original = tmp_path / "original.pdf"
    copied = tmp_path / "copied.pdf"
    make_invoice_pdf(original, number="SHA-01", total="99.50")
    copied.write_bytes(original.read_bytes())

    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)
    service.process_file(original)
    duplicate = service.process_file(copied)

    assert duplicate.status is InvoiceStatus.DUPLICATE
    assert "SHA-256" in duplicate.status_message


def test_exports_visible_columns_to_excel(tmp_path: Path) -> None:
    pdf = tmp_path / "export.pdf"
    output = tmp_path / "result.xlsx"
    make_invoice_pdf(pdf, number="EXPORT-01", total="12.34")
    service = InvoiceService(InvoiceRepository(tmp_path / "invoices.sqlite3"), TARGET)
    service.process_file(pdf)

    export_invoices(output, service.list_invoices(), service.summary())

    sheet = load_workbook(output, data_only=True).active
    assert sheet["A1"].value == "发票批量核验结果"
    assert sheet["B3"].value == "EXPORT-01"
    assert sheet["G3"].value == 12.34
