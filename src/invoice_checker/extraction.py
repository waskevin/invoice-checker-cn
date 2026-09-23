from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True, slots=True)
class PdfExtraction:
    text: str
    words: tuple[tuple[float, float, float, float, str], ...]


class PdfTextExtractor:
    """Layer 1: obtain native PDF text and word coordinates, without OCR."""

    def extract(self, path: Path) -> PdfExtraction:
        text_parts: list[str] = []
        words: list[tuple[float, float, float, float, str]] = []
        with pymupdf.open(path) as document:
            for page in document:
                # Different PDF producers disagree on text reading order.
                # Keep both variants: sorted text works for many generated
                # invoices, while native order preserves labels in two-column
                # layouts.  Parsers use coordinates when text order is weak.
                text_parts.append(page.get_text("text", sort=True))
                text_parts.append(page.get_text("text"))
                words.extend((x0, y0, x1, y1, word) for x0, y0, x1, y1, word, *_ in page.get_text("words", sort=True))
        text = "\n".join(text_parts).strip()
        if not text:
            raise ValueError("PDF 不包含可直接读取的文字；OCR 接口尚未配置")
        return PdfExtraction(text=text, words=tuple(words))
