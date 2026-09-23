from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .models import Invoice, InvoiceStatus
from .services import InvoiceService


@dataclass(frozen=True, slots=True)
class ShellImportBatch:
    invoices: tuple[Invoice, ...]
    valid_total: Decimal

    @property
    def copy_block_reason(self) -> str:
        buyers = {invoice.buyer_name for invoice in self.invoices}
        if not self.invoices or None in buyers:
            return "本批存在未识别的购买方，未复制金额合计"
        if len(buyers) != 1:
            return "本批发票购买方不一致，未复制金额合计"
        return ""

    @property
    def clipboard_total(self) -> str | None:
        if self.copy_block_reason:
            return None
        return f"{self.valid_total:.2f}"


def import_shell_selection(service: InvoiceService, paths: list[Path]) -> ShellImportBatch:
    """Import Explorer-selected PDFs and calculate only this invocation's valid total."""
    invoices = tuple(service.process_files(paths))
    valid_total = sum(
        (invoice.total_with_tax for invoice in invoices
         if invoice.status is InvoiceStatus.VALID and invoice.total_with_tax is not None),
        Decimal("0.00"),
    )
    return ShellImportBatch(invoices, valid_total)
