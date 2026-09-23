from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .extraction import PdfTextExtractor
from .hotkey import parse_hotkey
from .models import Invoice, InvoiceKind, InvoiceStatus, Summary
from .parsers import ChineseVatInvoiceParser
from .storage import InvoiceRepository
from .validation import validate_invoice


class InvoiceService:
    """Coordinates all layers; OCR can be plugged in after PdfTextExtractor fails."""

    def __init__(self, repository: InvoiceRepository, target_buyer: str, extractor: PdfTextExtractor | None = None,
                 auto_rename: bool = True, target_buyer_tax_id: str = "") -> None:
        self.repository = repository
        self.target_buyer = target_buyer
        self.target_buyer_tax_id = target_buyer_tax_id
        self.hotkey = repository.get_hotkey()
        self.extractor = extractor or PdfTextExtractor()
        self.parser = ChineseVatInvoiceParser()
        self.auto_rename = auto_rename

    def process_file(self, path: Path) -> Invoice:
        path = path.resolve()
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            extracted = self.extractor.extract(path)
            fields = self.parser.parse(extracted)
            invoice = Invoice(file_path=path, sha256=sha256, extracted_text=extracted.text, **fields)
            self.repository.discard_parse_failures_for_sha256(sha256)
            duplicate_reason = self.repository.duplicate_reason(invoice.number, sha256)
            validate_invoice(invoice, self.target_buyer, self.target_buyer_tax_id, duplicate_reason)
            if self.auto_rename and self._can_rename(invoice):
                invoice.file_path = self._rename_file(invoice)
        except Exception as error:
            invoice = Invoice(path, sha256, status=InvoiceStatus.PARSE_ERROR, status_message=str(error))
        self.repository.add(invoice)
        return invoice

    def process_files(self, paths: list[Path]) -> list[Invoice]:
        return [self.process_file(path) for path in paths if path.suffix.lower() == ".pdf"]

    def list_invoices(self) -> list[Invoice]:
        return self.repository.list_all()

    def set_target_buyer(self, buyer_name: str) -> None:
        buyer_name = buyer_name.strip()
        if not buyer_name:
            raise ValueError("核验抬头不能为空")
        self.repository.set_target_buyer(buyer_name)
        self.target_buyer = buyer_name

    def set_target_buyer_tax_id(self, tax_id: str) -> None:
        tax_id = tax_id.strip().upper()
        if not tax_id:
            raise ValueError("核验税号不能为空")
        self.repository.set_target_buyer_tax_id(tax_id)
        self.target_buyer_tax_id = tax_id

    def set_hotkey(self, hotkey: str) -> None:
        spec = parse_hotkey(hotkey)
        self.repository.set_hotkey(spec.display)
        self.hotkey = spec.display

    def hotkey_status(self) -> str:
        return self.repository.get_hotkey_status()

    def remove_files(self, paths: list[Path]) -> int:
        """Remove imported records only; original user files are never touched."""
        return self.repository.remove_by_file_paths(paths)

    def summary(self) -> Summary:
        return self.repository.summary()

    @staticmethod
    def _can_rename(invoice: Invoice) -> bool:
        return bool(invoice.buyer_name and invoice.issue_date and invoice.total_with_tax is not None
                    and invoice.invoice_kind is not InvoiceKind.UNKNOWN)

    @staticmethod
    def _rename_file(invoice: Invoice) -> Path:
        """Rename without overwriting a sibling; append _2, _3, ... on collision."""
        safe_buyer = re.sub(r'[<>:"/\\|?*]', "_", invoice.buyer_name or "未知抬头").strip(" .")
        safe_seller = re.sub(r'[<>:"/\\|?*]', "_", invoice.seller_name or "未知销售方").strip(" .")
        amount = f"{invoice.total_with_tax:.2f}"
        stem = f"{safe_buyer}_{safe_seller}_{invoice.issue_date.isoformat()}_{invoice.invoice_kind.value}_{amount}"
        suffix = invoice.file_path.suffix.lower() or ".pdf"
        candidate = invoice.file_path.with_name(stem + suffix)
        sequence = 2
        while candidate.exists() and candidate != invoice.file_path:
            candidate = invoice.file_path.with_name(f"{stem}_{sequence}{suffix}")
            sequence += 1
        return invoice.file_path if candidate == invoice.file_path else invoice.file_path.rename(candidate)
