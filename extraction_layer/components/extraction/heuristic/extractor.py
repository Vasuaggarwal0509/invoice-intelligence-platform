"""
HeuristicExtractor — the G1 + G2 baseline extractor.

Combines three stages, every one of them designed against observations from
the 2026-04-18 visual spot-check:

  G1 - Regex rules (`regex_patterns.py`):
    * `invoice_no`      — anchored on "Invoice no" / "Invoiceno" / "Invoicen0"
    * `invoice_date`    — anchored on "Date of issue" (fallback: bare date)
    * `iban`            — anchored on "IBAN"
    * `seller_tax_id`   — tax-id regex *inside* the seller column
    * `client_tax_id`   — tax-id regex *inside* the client column

  G2 - Label-anchor dictionary (`labels.py`) + rapidfuzz fuzzy matching:
    * locating "Seller:" / "Client:" anchor lines for the column split
    * locating the "ITEMS" row that closes the seller / client block
    * filtering tax-id / iban lines out of aggregated address text

  Column detection (`columns.py`):
    * separates OCR lines into the left (seller) and right (client) columns
    * allows `seller` / `client` multi-line addresses to be aggregated
      from their respective columns only.

The extractor emits an `ExtractionResult` with seven fields from the
katanaml ground-truth schema (`invoice_no`, `invoice_date`, `seller`,
`client`, `seller_tax_id`, `client_tax_id`, `iban`). Line items are
intentionally out of scope — they belong to Component H (tables).
"""

import time

from extraction_layer.components.ocr.types import OCRResult

from ..base import BaseExtractor
from ..types import ExtractedField, ExtractionResult
from .columns import ColumnLayout, detect_columns
from .labels import line_contains_label, line_is_label
from .normalizers import normalize_address_spacing
from .regex_patterns import (
    DATE_ANCHORED,
    DATE_BARE,
    IBAN_ANCHORED,
    IBAN_BARE,
    INVOICE_NO,
    INVOICE_NO_BARE,
    TAX_ID_ANCHORED,
    TAX_ID_BARE,
)


# Confidence tiers. Anchored regex = high (the label + format both matched).
# Column-scoped regex = medium-high (format matched in expected location).
# Bare regex = medium (format matched without anchor — some risk of wrong pick).
# Column-aggregated text = medium (multiline stitching is inherently fuzzier).
_CONF_ANCHORED = 0.95
_CONF_COLUMN_SCOPED = 0.90
_CONF_BARE = 0.70
_CONF_AGGREGATE = 0.75
_CONF_NONE = 0.0


class HeuristicExtractor(BaseExtractor):
    """Regex + column-heuristic extractor for katanaml-style invoices."""

    @property
    def extractor_name(self) -> str:
        return "heuristic"

    def extract(self, ocr_result: OCRResult) -> ExtractionResult:
        start = time.perf_counter()

        columns = detect_columns(ocr_result)

        fields: dict[str, ExtractedField] = {
            "invoice_no": self._extract_invoice_no(ocr_result),
            "invoice_date": self._extract_invoice_date(ocr_result),
            "iban": self._extract_iban(ocr_result),
            "seller_tax_id": self._extract_tax_id_in_column(
                ocr_result, columns.left_indices, "seller_tax_id"
            ),
            "client_tax_id": self._extract_tax_id_in_column(
                ocr_result, columns.right_indices, "client_tax_id"
            ),
            "seller": self._aggregate_address(
                ocr_result, columns.left_indices, "seller"
            ),
            "client": self._aggregate_address(
                ocr_result, columns.right_indices, "client"
            ),
        }

        duration_ms = (time.perf_counter() - start) * 1000.0
        return ExtractionResult(
            fields=fields,
            extractor=self.extractor_name,
            duration_ms=duration_ms,
            diagnostics={
                "column_split_x": columns.split_x,
                "seller_anchor_y": columns.seller_anchor_y,
                "client_anchor_y": columns.client_anchor_y,
                "items_start_y": columns.items_start_y,
                "left_line_count": len(columns.left_indices),
                "right_line_count": len(columns.right_indices),
            },
        )

    # ----- Global-scope regex fields --------------------------------------

    def _extract_invoice_no(self, ocr_result: OCRResult) -> ExtractedField:
        for line in ocr_result.lines:
            m = INVOICE_NO.search(line.text)
            if m:
                return ExtractedField(
                    name="invoice_no",
                    value=m.group("value"),
                    confidence=_CONF_ANCHORED,
                    source="regex",
                    source_detail="invoice_no anchor",
                )
        # Fallback: a bare numeric line right after an Invoice anchor line.
        for i, line in enumerate(ocr_result.lines):
            if line_contains_label(line.text, "invoice_no"):
                # Peek at the next line for a bare number.
                if i + 1 < len(ocr_result.lines):
                    m = INVOICE_NO_BARE.match(ocr_result.lines[i + 1].text)
                    if m:
                        return ExtractedField(
                            name="invoice_no",
                            value=m.group("value"),
                            confidence=_CONF_BARE,
                            source="regex",
                            source_detail="invoice_no bare (following anchor)",
                        )
        return _none_field("invoice_no")

    def _extract_invoice_date(self, ocr_result: OCRResult) -> ExtractedField:
        for line in ocr_result.lines:
            m = DATE_ANCHORED.search(line.text)
            if m:
                return ExtractedField(
                    name="invoice_date",
                    value=m.group("value"),
                    confidence=_CONF_ANCHORED,
                    source="regex",
                    source_detail="date anchored",
                )
        # Fallback: a bare date on the line immediately after a "Date" label.
        for i, line in enumerate(ocr_result.lines):
            if line_contains_label(line.text, "date") and i + 1 < len(ocr_result.lines):
                m = DATE_BARE.match(ocr_result.lines[i + 1].text)
                if m:
                    return ExtractedField(
                        name="invoice_date",
                        value=m.group("value"),
                        confidence=_CONF_BARE,
                        source="regex",
                        source_detail="date bare (following anchor)",
                    )
        return _none_field("invoice_date")

    def _extract_iban(self, ocr_result: OCRResult) -> ExtractedField:
        for line in ocr_result.lines:
            m = IBAN_ANCHORED.search(line.text)
            if m:
                return ExtractedField(
                    name="iban",
                    value=m.group("value").upper(),
                    confidence=_CONF_ANCHORED,
                    source="regex",
                    source_detail="IBAN anchored",
                )
        # Fallback: bare IBAN-shape somewhere in the document.
        for line in ocr_result.lines:
            m = IBAN_BARE.search(line.text)
            if m:
                return ExtractedField(
                    name="iban",
                    value=m.group("value").upper(),
                    confidence=_CONF_BARE,
                    source="regex",
                    source_detail="IBAN bare",
                )
        return _none_field("iban")

    # ----- Column-scoped fields -------------------------------------------

    def _extract_tax_id_in_column(
        self,
        ocr_result: OCRResult,
        column_indices: list[int],
        field_name: str,
    ) -> ExtractedField:
        for idx in column_indices:
            line = ocr_result.lines[idx]
            m = TAX_ID_ANCHORED.search(line.text)
            if m:
                return ExtractedField(
                    name=field_name,
                    value=m.group("value"),
                    confidence=_CONF_COLUMN_SCOPED,
                    source="regex",
                    source_detail="tax_id anchored in column",
                )
        # Fallback: bare tax-id pattern inside the column.
        for idx in column_indices:
            line = ocr_result.lines[idx]
            m = TAX_ID_BARE.search(line.text)
            if m:
                return ExtractedField(
                    name=field_name,
                    value=m.group("value"),
                    confidence=_CONF_BARE,
                    source="regex",
                    source_detail="tax_id bare in column",
                )
        return _none_field(field_name)

    def _aggregate_address(
        self,
        ocr_result: OCRResult,
        column_indices: list[int],
        field_name: str,
    ) -> ExtractedField:
        """Stitch multi-line address text from a column, skipping tax-id and iban lines."""
        if not column_indices:
            return _none_field(field_name)

        parts: list[str] = []
        for idx in column_indices:
            text = ocr_result.lines[idx].text.strip()
            if not text:
                continue
            # Skip label-only lines that sneaked in.
            if line_is_label(text, "seller") or line_is_label(text, "client"):
                continue
            # Skip lines that are primarily tax-id or iban.
            if _is_tax_id_line(text) or _is_iban_line(text):
                continue
            parts.append(text)

        if not parts:
            return _none_field(field_name)

        raw = " ".join(parts)
        normalised = normalize_address_spacing(raw)
        return ExtractedField(
            name=field_name,
            value=normalised,
            confidence=_CONF_AGGREGATE,
            source="column_heuristic",
            source_detail="column-aggregated address + space-normalised",
        )


# ----- helpers --------------------------------------------------------------


def _none_field(name: str) -> ExtractedField:
    return ExtractedField(
        name=name,
        value=None,
        confidence=_CONF_NONE,
        source="none",
        source_detail=None,
    )


def _is_tax_id_line(text: str) -> bool:
    """Line is primarily a tax-id (value + optional label)."""
    if TAX_ID_ANCHORED.search(text):
        return True
    # Bare tax-id pattern alone on a short line is also "a tax-id line".
    m = TAX_ID_BARE.search(text)
    if m and len(text.strip()) <= len(m.group("value")) + 4:
        return True
    return line_contains_label(text, "tax_id")


def _is_iban_line(text: str) -> bool:
    """Line is primarily an IBAN (value + optional label)."""
    if IBAN_ANCHORED.search(text):
        return True
    if line_contains_label(text, "iban"):
        return True
    return False


# Silence unused-import hint — `ColumnLayout` is re-exported here for convenience.
_ = ColumnLayout
