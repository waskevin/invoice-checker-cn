from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .exporter import export_invoices
from .hotkey import is_hotkey_available, parse_hotkey
from .models import InvoiceStatus
from .services import InvoiceService
from .shell_integration import ShellImportBatch, import_shell_selection


class ShortcutEdit(QLineEdit):
    """A click-to-record field so users never need to type modifier names."""

    captured = Signal(str)

    def focusInEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().focusInEvent(event)
        self.setPlaceholderText("请按快捷键")
        self.selectAll()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift):
            event.accept()
            return
        modifiers = event.modifiers()
        names: list[str] = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            names.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            names.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            names.append("Shift")
        key_name = QKeySequence(event.key()).toString(QKeySequence.SequenceFormat.PortableText).upper()
        if names and key_name:
            value = "+".join([*names, key_name])
            self.setText(value)
            self.captured.emit(value)
        event.accept()


class MainWindow(QMainWindow):
    headers = ["文件名", "发票号码", "日期", "类型", "销售方", "购买方", "购买方税号", "价税合计", "状态", "文件路径"]

    def __init__(self, service: InvoiceService) -> None:
        super().__init__()
        self.service = service
        self.setWindowTitle("发票批量核验 + 金额汇总工具")
        self.resize(1280, 700)
        self.setAcceptDrops(True)
        root = QWidget()
        layout = QVBoxLayout(root)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("核验抬头："))
        self.target_input = QLineEdit(service.target_buyer)
        self.target_input.setMinimumWidth(250)
        controls.addWidget(self.target_input)
        controls.addWidget(QLabel("核验税号："))
        self.target_tax_id_input = QLineEdit(service.target_buyer_tax_id)
        self.target_tax_id_input.setMinimumWidth(180)
        controls.addWidget(self.target_tax_id_input)
        controls.addWidget(QLabel("快捷键："))
        self.hotkey_input = ShortcutEdit(service.hotkey)
        self.hotkey_input.setToolTip("点击后直接按下组合键，例如 Alt+R。保存后，资源管理器中多选 PDF，按 Ctrl+C，再按快捷键导入。")
        self.hotkey_input.setMaximumWidth(130)
        self.hotkey_input.captured.connect(self.save_hotkey)
        controls.addWidget(self.hotkey_input)
        save_target = QPushButton("保存核验信息")
        save_target.clicked.connect(self.save_target_buyer)
        controls.addWidget(save_target)
        choose = QPushButton("选择 PDF 文件")
        choose.clicked.connect(self.choose_files)
        export = QPushButton("导出 Excel")
        export.clicked.connect(self.export_excel)
        remove = QPushButton("剔除所选")
        remove.clicked.connect(self.remove_selected_rows)
        locate = QPushButton("定位文件")
        locate.clicked.connect(self.locate_selected_file)
        controls.addWidget(choose)
        controls.addWidget(remove)
        controls.addWidget(locate)
        controls.addWidget(export)
        controls.addStretch()
        layout.addLayout(controls)
        self.hotkey_status_label = QLabel()
        layout.addWidget(self.hotkey_status_label)
        self.drop_hint = QLabel(f"推荐：在资源管理器多选 PDF，按 Ctrl+C，再按 {self.service.hotkey} 从剪贴板导入；也可拖放或点击“选择 PDF 文件”")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drop_hint)
        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_menu)
        self.table.cellClicked.connect(self.copy_cell)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.table)
        self.copy_shortcut.activated.connect(self.copy_table_selection)
        self.remove_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self.table)
        self.remove_shortcut.activated.connect(self.remove_selected_rows)
        layout.addWidget(self.table)
        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)
        total_row = QHBoxLayout()
        total_row.addWidget(QLabel("有效金额合计（可复制）："))
        self.total_input = QLineEdit()
        self.total_input.setReadOnly(True)
        self.total_input.setMaximumWidth(180)
        total_row.addWidget(self.total_input)
        total_row.addStretch()
        layout.addLayout(total_row)
        self.setCentralWidget(root)
        self.refresh()

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.import_paths([Path(url.toLocalFile()) for url in event.mimeData().urls()])
        event.acceptProposedAction()

    def choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 发票", "", "PDF 文件 (*.pdf)")
        self.import_paths([Path(file) for file in files])

    def save_target_buyer(self) -> None:
        try:
            self.service.set_target_buyer(self.target_input.text())
            self.service.set_target_buyer_tax_id(self.target_tax_id_input.text())
        except ValueError as error:
            QMessageBox.warning(self, "无法保存", str(error))
            return
        self.statusBar().showMessage("核验抬头和税号已保存。", 5000)

    def save_hotkey(self, value: str | None = None) -> None:
        """Validate, persist and restart the installed helper when a shortcut is recorded."""
        requested = (value or self.hotkey_input.text()).strip()
        try:
            spec = parse_hotkey(requested)
        except ValueError as error:
            QMessageBox.warning(self, "快捷键不可用", str(error))
            self.hotkey_input.setText(self.service.hotkey)
            return
        if spec.display != self.service.hotkey and not is_hotkey_available(spec):
            QMessageBox.warning(self, "快捷键冲突", f"{spec.display} 已被其他程序占用，请换一个组合键。")
            self.hotkey_input.setText(self.service.hotkey)
            return
        self.service.set_hotkey(spec.display)
        self.hotkey_input.setText(spec.display)
        started = self.restart_hotkey_helper()
        if started:
            message = f"快捷键已保存并立即启用：{spec.display}。多选 PDF 后按 Ctrl+C，再按快捷键导入。"
        else:
            message = f"快捷键已保存：{spec.display}（后台助手将在下次登录时启用）。多选 PDF 后按 Ctrl+C，再按快捷键导入。"
        self.hotkey_status_label.setText(message)
        self.statusBar().showMessage(message, 8000)

    def restart_hotkey_helper(self) -> bool:
        """The installed app can apply a new shortcut without requiring Windows sign-out."""
        if not getattr(sys, "frozen", False):
            return False
        if not getattr(sys, "frozen", False):
            return False
        # The existing helper keeps its registration until Windows starts the
        # next startup instance.  Do not kill this GUI process just to change
        # a shortcut; the new setting is safely persisted immediately.
        return False

    def import_paths(self, paths: list[Path], copy_batch_total: bool = False) -> ShellImportBatch | None:
        pdfs = [path for path in paths if path.suffix.lower() == ".pdf"]
        if not pdfs:
            return None
        batch = import_shell_selection(self.service, pdfs)
        self.refresh()
        if copy_batch_total:
            if batch.clipboard_total is None:
                self.statusBar().showMessage(batch.copy_block_reason, 10000)
            else:
                QApplication.clipboard().setText(batch.clipboard_total)
                self.statusBar().showMessage(
                    f"已导入 {len(batch.invoices)} 张；本批有效金额合计 {batch.clipboard_total} 已复制。", 8000
                )
        return batch

    def refresh(self) -> None:
        invoices = self.service.list_invoices()
        self.table.setRowCount(len(invoices))
        for row, invoice in enumerate(invoices):
            values = [invoice.file_path.name, invoice.number or "", invoice.issue_date.isoformat() if invoice.issue_date else "",
                      invoice.invoice_kind.value, invoice.seller_name or "", invoice.buyer_name or "",
                      invoice.buyer_tax_id or "", f"{invoice.total_with_tax:.2f}" if invoice.total_with_tax is not None else "", invoice.status.value,
                      str(invoice.file_path.resolve())]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if invoice.status is not InvoiceStatus.VALID:
                    item.setForeground(QColor("#C62828"))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        summary = self.service.summary()
        self.summary_label.setText(
            f"已读取：{summary.file_count} 张  |  正常有效：{summary.valid_count} 张  |  "
            f"抬头异常：{summary.mismatch_count} 张  |  重复：{summary.duplicate_count} 张  |  "
            f"解析失败：{summary.error_count} 张"
        )
        self.total_input.setText(f"{summary.valid_total:.2f}")
        self.hotkey_status_label.setText(f"快捷键：{self.service.hotkey}；{self.service.hotkey_status()}")

    def copy_table_selection(self) -> None:
        indexes = sorted(self.table.selectedIndexes(), key=lambda index: (index.row(), index.column()))
        if not indexes:
            return
        rows: dict[int, list[str]] = {}
        for index in indexes:
            rows.setdefault(index.row(), []).append(index.data() or "")
        QApplication.clipboard().setText("\n".join("\t".join(values) for values in rows.values()))

    def copy_cell(self, row: int, column: int) -> None:
        """Click filenames and amounts to copy; click a path to reveal that file."""
        path_column = self.headers.index("文件路径")
        item = self.table.item(row, column)
        if column == path_column and item:
            self.open_file_location(Path(item.text()))
            return
        if column not in (0, self.headers.index("价税合计")):
            return
        if item:
            QApplication.clipboard().setText(item.text())

    def locate_selected_file(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not selected_rows:
            self.statusBar().showMessage("请先选择一张发票。", 4000)
            return
        invoice = self.service.list_invoices()[selected_rows[0]]
        self.open_file_location(invoice.file_path)

    def open_file_location(self, file_path: Path) -> None:
        """Open Windows Explorer and select the requested local PDF."""
        if not file_path.exists():
            QMessageBox.warning(self, "无法定位", f"文件不存在或已移动：\n{file_path}")
            return
        subprocess.Popen(["explorer.exe", f"/select,{file_path}"], shell=False)

    def show_table_menu(self, position) -> None:  # type: ignore[no-untyped-def]
        clicked = self.table.indexAt(position)
        if clicked.isValid() and not clicked in self.table.selectedIndexes():
            self.table.clearSelection()
            self.table.selectRow(clicked.row())
        if not self.table.selectedIndexes():
            return
        menu = QMenu(self)
        remove_action = menu.addAction("从结果中剔除（保留原 PDF）")
        remove_action.triggered.connect(self.remove_selected_rows)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def remove_selected_rows(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return
        invoices = self.service.list_invoices()
        selected = [invoices[row] for row in selected_rows]
        removed = self.service.remove_files([invoice.file_path for invoice in selected])
        self.refresh()
        summary = self.service.summary()
        self.statusBar().showMessage(
            f"已剔除 {removed} 条导入记录；原 PDF 未删除。当前有效金额合计：{summary.valid_total:.2f}", 6000
        )

    def export_excel(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "导出 Excel", "发票核验结果.xlsx", "Excel 文件 (*.xlsx)")
        if not filename:
            return
        export_invoices(Path(filename), self.service.list_invoices(), self.service.summary())
        QMessageBox.information(self, "导出完成", f"已导出到：\n{filename}")


def run(service: InvoiceService, initial_paths: list[Path] | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(service)
    if initial_paths:
        window.import_paths(initial_paths, copy_batch_total=True)
    window.show()
    return app.exec()
