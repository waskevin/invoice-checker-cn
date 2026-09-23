from __future__ import annotations

from .models import Invoice, InvoiceStatus


def validate_invoice(invoice: Invoice, target_buyer: str, target_buyer_tax_id: str,
                     duplicate_reason: str | None = None) -> Invoice:
    """Layer 3: apply business rules in a deterministic order."""
    required = (invoice.number, invoice.issue_date, invoice.buyer_name, invoice.total_with_tax)
    if not all(value is not None for value in required):
        invoice.status = InvoiceStatus.PARSE_ERROR
        invoice.status_message = "缺少发票号码、日期、购买方或价税合计（小写）"
    elif invoice.buyer_name != target_buyer:
        invoice.status = InvoiceStatus.BUYER_MISMATCH
        invoice.status_message = f"购买方为“{invoice.buyer_name}”，与目标抬头不一致"
    elif target_buyer_tax_id and not invoice.buyer_tax_id:
        invoice.status = InvoiceStatus.BUYER_MISMATCH
        invoice.status_message = "购买方税号缺失"
    elif target_buyer_tax_id and invoice.buyer_tax_id != target_buyer_tax_id:
        invoice.status = InvoiceStatus.BUYER_MISMATCH
        invoice.status_message = f"购买方税号为“{invoice.buyer_tax_id}”，与目标税号不一致"
    elif duplicate_reason:
        invoice.status = InvoiceStatus.DUPLICATE
        invoice.status_message = duplicate_reason
    else:
        invoice.status = InvoiceStatus.VALID
        invoice.status_message = "抬头、税号与关键字段核验通过"
    return invoice
