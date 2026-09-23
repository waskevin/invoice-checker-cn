from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path


class InvoiceKind(str, Enum):
    ORDINARY = "普票"
    SPECIAL = "专票"
    UNKNOWN = "未识别"


class InvoiceStatus(str, Enum):
    VALID = "正常有效"
    BUYER_MISMATCH = "抬头不符"
    DUPLICATE = "重复票"
    PARSE_ERROR = "解析失败"


@dataclass(slots=True)
class Invoice:
    file_path: Path
    sha256: str
    number: str | None = None
    issue_date: date | None = None
    invoice_kind: InvoiceKind = InvoiceKind.UNKNOWN
    buyer_name: str | None = None
    buyer_tax_id: str | None = None
    seller_name: str | None = None
    total_with_tax: Decimal | None = None
    status: InvoiceStatus = InvoiceStatus.PARSE_ERROR
    status_message: str = ""
    extracted_text: str = ""


@dataclass(frozen=True, slots=True)
class Summary:
    file_count: int
    valid_count: int
    mismatch_count: int
    duplicate_count: int
    error_count: int
    valid_total: Decimal
