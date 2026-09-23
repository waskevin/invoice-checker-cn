import argparse
from pathlib import Path

from .gui import run
from .services import InvoiceService
from .storage import InvoiceRepository


def parse_command_line(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="发票批量核验 + 金额汇总工具")
    parser.add_argument("--hotkey-helper", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("pdf_files", nargs="*", type=Path, help="由 Windows 右键菜单传入的 PDF")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_command_line(argv)
    if args.hotkey_helper:
        from .hotkey_helper import main as run_hotkey_helper
        return run_hotkey_helper()
    application_data = Path.home() / "AppData" / "Local" / "InvoiceChecker"
    repository = InvoiceRepository(application_data / "invoices.sqlite3")
    target_buyer = repository.get_target_buyer("示例购买方有限公司")
    target_buyer_tax_id = repository.get_target_buyer_tax_id("91310000000000000X")
    return run(InvoiceService(repository, target_buyer, target_buyer_tax_id=target_buyer_tax_id), args.pdf_files)


if __name__ == "__main__":
    raise SystemExit(main())
