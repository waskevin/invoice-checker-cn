from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .extraction import PdfExtraction
from .models import InvoiceKind


class ChineseVatInvoiceParser:
    """Layer 2: parser for common electronic Chinese VAT invoice layouts."""

    _date = re.compile(r"开票日期\s*[：:]?\s*(20\d{2})\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})")
    _number = re.compile(r"(?:发票号码|发票号)\s*[：:]?\s*(\d{20}|[A-Za-z0-9-]{6,32})")
    _total = re.compile(r"(?:价税合计\s*[（(]小写[）)]|[（(]小写[）)])\s*[：:]?\s*(?:￥|¥|RMB)?\s*([\d,]+(?:\.\d{1,2})?)")

    def parse(self, extracted: PdfExtraction) -> dict[str, object]:
        text = re.sub(r"[\u3000\t]", " ", extracted.text)
        coordinate_buyer, coordinate_seller = self._coordinate_party_names(extracted.words)
        coordinate_buyer_tax_id = self._coordinate_party_tax_id(extracted.words)
        coordinate_number = self._coordinate_value(extracted.words, "发票号码", r"\d{20}")
        coordinate_date = self._coordinate_value(extracted.words, "开票日期", r"20\d{2}[年/-]\d{1,2}[月/-]\d{1,2}")
        return {
            "number": self._match(self._number, text) or coordinate_number,
            "issue_date": self._parse_date(text) or self._parse_date(f"开票日期：{coordinate_date}"),
            "invoice_kind": self._kind(text),
            "buyer_name": self._party_name(text, "购买方信息", "销售方信息") or self._split_party_name(text, r"购[\s\S]{0,80}?买") or coordinate_buyer,
            "buyer_tax_id": self._party_tax_id(text, "购买方信息", "销售方信息") or coordinate_buyer_tax_id,
            "seller_name": self._party_name(text, "销售方信息", None) or self._split_party_name(text, r"销[\s\S]{0,80}?售") or coordinate_seller,
            "total_with_tax": self._parse_total(text),
        }

    @staticmethod
    def _match(pattern: re.Pattern[str], text: str) -> str | None:
        matched = pattern.search(text)
        return matched.group(1).strip() if matched else None

    def _parse_date(self, text: str) -> date | None:
        matched = self._date.search(text)
        if not matched:
            return None
        year, month, day = map(int, matched.groups())
        return date(year, month, day)

    def _parse_total(self, text: str) -> Decimal | None:
        value = self._match(self._total, text)
        if not value:
            return None
        try:
            return Decimal(value.replace(",", ""))
        except InvalidOperation:
            return None

    @staticmethod
    def _kind(text: str) -> InvoiceKind:
        if "专用发票" in text or "专票" in text:
            return InvoiceKind.SPECIAL
        if "普通发票" in text or "普票" in text:
            return InvoiceKind.ORDINARY
        return InvoiceKind.UNKNOWN

    @staticmethod
    def _party_name(text: str, start: str, end: str | None) -> str | None:
        start_index = text.find(start)
        if start_index < 0:
            return None
        section = text[start_index + len(start):]
        if end and (end_index := section.find(end)) >= 0:
            section = section[:end_index]
        matched = re.search(r"名称\s*[：:]?\s*([^\s\n\r]+)", section)
        return matched.group(1).strip() if matched else None

    @staticmethod
    def _split_party_name(text: str, party_marker: str) -> str | None:
        """Support PDFs that place buyer and seller labels in vertical columns."""
        matched = re.search(rf"{party_marker}\s*名称\s*[：:]?\s*([^\s\n\r]+)", text)
        return matched.group(1).strip() if matched else None

    @staticmethod
    def _party_tax_id(text: str, start: str, end: str | None) -> str | None:
        start_index = text.find(start)
        if start_index < 0:
            return None
        section = text[start_index + len(start):]
        if end and (end_index := section.find(end)) >= 0:
            section = section[:end_index]
        matched = re.search(r"统一社会信用代码/纳税人识别号\s*[：:]?\s*([0-9A-Z]{15,20})", section)
        return matched.group(1) if matched else None

    @staticmethod
    def _coordinate_party_names(words: tuple[tuple[float, float, float, float, str], ...]) -> tuple[str | None, str | None]:
        """Read the left/right buyer and seller columns when PDF text order is broken.

        Some e-invoices draw ``购 买 方`` and ``销 售 方`` vertically.  Their
        extracted text puts headings before values, but word coordinates retain
        the visual two-column layout.  A name is the nearest Chinese text to
        the right of a ``名称`` label on the same row.
        """
        candidates: list[tuple[float, str]] = []
        for x0, y0, x1, y1, word in words:
            normalized = word.replace(" ", "")
            if normalized not in {"名称:", "名称：", "称:", "称："}:
                continue
            label_center_y = (y0 + y1) / 2
            names = [
                (other_x0, other_word)
                for other_x0, other_y0, _, other_y1, other_word in words
                if other_x0 >= x0 + 15
                and abs(((other_y0 + other_y1) / 2) - label_center_y) <= 12
                and re.search(r"[\u4e00-\u9fff]", other_word)
                and "名称" not in other_word
                and other_word not in {"名", "称", "称:", "称："}
            ]
            if names:
                _, name = min(names, key=lambda item: item[0])
                candidates.append((x0, name.strip()))

        # Standard VAT invoice layouts always place the buyer column on the
        # left and seller column on the right.
        unique = sorted({item for item in candidates}, key=lambda item: item[0])
        if len(unique) < 2:
            return None, None
        return unique[0][1], unique[-1][1]

    @staticmethod
    def _coordinate_value(words: tuple[tuple[float, float, float, float, str], ...], label: str,
                          pattern: str) -> str | None:
        """Find a field value to the right of its label in the same row."""
        for x0, y0, x1, y1, word in words:
            if label not in word:
                continue
            label_center_y = (y0 + y1) / 2
            for other_x0, other_y0, _, other_y1, other_word in words:
                if other_x0 < x1 - 2 or abs(((other_y0 + other_y1) / 2) - label_center_y) > 12:
                    continue
                matched = re.search(pattern, other_word)
                if matched:
                    return matched.group(0)
        return None

    @staticmethod
    def _coordinate_party_tax_id(words: tuple[tuple[float, float, float, float, str], ...]) -> str | None:
        labeled_tax_ids: list[tuple[float, str]] = []
        for x0, _, _, _, word in words:
            if "纳税人识别号" not in word and "社会信用代码" not in word:
                continue
            matched = re.search(r"([0-9A-Z]{15,20})", word)
            if matched:
                labeled_tax_ids.append((x0, matched.group(1)))
        if labeled_tax_ids:
            return sorted(labeled_tax_ids, key=lambda item: item[0])[0][1]

        tax_ids = sorted(
            (x0, word) for x0, _, _, _, word in words if re.fullmatch(r"[0-9A-Z]{15,20}", word)
        )
        # On standard invoice layouts buyer information is the left column.
        return tax_ids[0][1] if tax_ids else None
