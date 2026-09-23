from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from .models import Invoice, InvoiceKind, InvoiceStatus, Summary


class InvoiceRepository:
    """Layer 4: local SQLite persistence and duplicate lookup."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY, file_path TEXT NOT NULL, sha256 TEXT NOT NULL,
                number TEXT, issue_date TEXT, invoice_kind TEXT NOT NULL, buyer_name TEXT,
                buyer_tax_id TEXT,
                seller_name TEXT, total_with_tax TEXT, status TEXT NOT NULL,
                status_message TEXT NOT NULL, extracted_text TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(number)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_invoices_sha256 ON invoices(sha256)")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
            if "buyer_tax_id" not in columns:
                db.execute("ALTER TABLE invoices ADD COLUMN buyer_tax_id TEXT")

    def get_target_buyer(self, default: str) -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'target_buyer'").fetchone()
        return row["value"] if row else default

    def set_target_buyer(self, buyer_name: str) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO settings(key, value) VALUES ('target_buyer', ?)
                          ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (buyer_name,))

    def get_target_buyer_tax_id(self, default: str) -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'target_buyer_tax_id'").fetchone()
        return row["value"] if row else default

    def set_target_buyer_tax_id(self, tax_id: str) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO settings(key, value) VALUES ('target_buyer_tax_id', ?)
                          ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (tax_id,))

    def get_hotkey(self, default: str = "Alt+R") -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'hotkey'").fetchone()
        return row["value"] if row else default

    def set_hotkey(self, hotkey: str) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO settings(key,value) VALUES ('hotkey', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (hotkey,))

    def get_hotkey_status(self, default: str = "后台助手将在登录后启用快捷键；推荐多选 PDF 后按 Ctrl+C，再按快捷键从剪贴板导入。") -> str:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'hotkey_status'").fetchone()
        return row["value"] if row else default

    def duplicate_reason(self, number: str | None, sha256: str) -> str | None:
        with self._connect() as db:
            if db.execute("SELECT 1 FROM invoices WHERE sha256 = ? LIMIT 1", (sha256,)).fetchone():
                return "与已导入文件 SHA-256 相同"
            if number and db.execute("SELECT 1 FROM invoices WHERE number = ? LIMIT 1", (number,)).fetchone():
                return "与已导入发票号码相同"
        return None

    def discard_parse_failures_for_sha256(self, sha256: str) -> None:
        """Permit re-processing after a parser upgrade without creating a false duplicate."""
        with self._connect() as db:
            db.execute("DELETE FROM invoices WHERE sha256 = ? AND status = ?", (sha256, InvoiceStatus.PARSE_ERROR.value))

    def add(self, invoice: Invoice) -> None:
        with self._connect() as db:
            db.execute("""INSERT INTO invoices
                (file_path, sha256, number, issue_date, invoice_kind, buyer_name, buyer_tax_id, seller_name,
                 total_with_tax, status, status_message, extracted_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(invoice.file_path), invoice.sha256, invoice.number,
                 invoice.issue_date.isoformat() if invoice.issue_date else None,
                 invoice.invoice_kind.value, invoice.buyer_name, invoice.buyer_tax_id, invoice.seller_name,
                 str(invoice.total_with_tax) if invoice.total_with_tax is not None else None,
                 invoice.status.value, invoice.status_message, invoice.extracted_text))

    def remove_by_file_paths(self, paths: list[Path]) -> int:
        if not paths:
            return 0
        with self._connect() as db:
            before = db.total_changes
            db.executemany("DELETE FROM invoices WHERE file_path = ?", [(str(path.resolve()),) for path in paths])
            return db.total_changes - before

    def list_all(self) -> list[Invoice]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM invoices ORDER BY id").fetchall()
        return [self._from_row(row) for row in rows]

    def summary(self) -> Summary:
        invoices = self.list_all()
        valid = [item for item in invoices if item.status is InvoiceStatus.VALID and item.total_with_tax is not None]
        return Summary(len(invoices), len(valid), sum(item.status is InvoiceStatus.BUYER_MISMATCH for item in invoices),
                       sum(item.status is InvoiceStatus.DUPLICATE for item in invoices),
                       sum(item.status is InvoiceStatus.PARSE_ERROR for item in invoices),
                       sum((item.total_with_tax for item in valid), Decimal("0.00")))

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Invoice:
        from datetime import date
        return Invoice(Path(row["file_path"]), row["sha256"], row["number"],
                       date.fromisoformat(row["issue_date"]) if row["issue_date"] else None,
                       InvoiceKind(row["invoice_kind"]), row["buyer_name"], row["buyer_tax_id"], row["seller_name"],
                       Decimal(row["total_with_tax"]) if row["total_with_tax"] else None,
                       InvoiceStatus(row["status"]), row["status_message"], row["extracted_text"])
