"""
SpatialTableExtractor — H1 baseline for Component H.

Reconstructs invoice line items from OCR line bboxes using pure spatial
clustering. No ML, no training data. See `research.md` §10 for the rationale
and `progress.md` 2026-04-18 for the path-selection notes.

Algorithm (value-pattern based — robust to the occasional missing column
in OCR output):

  1. Bound the items region between the ITEMS anchor and the SUMMARY
     anchor (reusing `components.extraction.heuristic.labels`).
  2. Detect item anchors inside that region — OCR lines whose text matches
     ``\\d+\\.`` (e.g. "1.", "2.", "3.") in the leftmost column.
  3. For each item anchor, collect the OCR lines on the same y-band
     (anchor line height \u00b1 70% tolerance).
  4. Classify each band line by its value pattern:
        - decimal with comma (``889,20``) \u2192 numeric column
        - ``\\d+\\s*%`` \u2192 VAT column
        - ``each`` / ``pcs`` etc \u2192 UM column (not emitted; used for filtering)
        - everything else to the right of the anchor \u2192 description line 1
  5. Sort the decimal values by x-coordinate: the 4 expected are Qty \u2192
     Net price \u2192 Net worth \u2192 Gross worth.
  6. Collect description continuation lines: lines below the anchor band,
     above the next item's anchor (or SUMMARY), whose x sits inside the
     description column range.
  7. Emit one ``InvoiceItem`` per anchor.

This works because every katanaml invoice uses the same column ordering
(see `research.md` §10.2). For multi-template data we escalate to the
scaffolded PP-Structure or LayoutLM backends.
"""

import re
import time

from extraction_layer.components._common.invoice_anchors import (
    ITEMS_START_VARIANTS,
    SUMMARY_START_VARIANTS,
)
from extraction_layer.components._common.text import matches_variant, normalize_multiword_spacing
from extraction_layer.components.ocr.types import Line, OCRResult

from ..base import BaseTableExtractor
from ..types import InvoiceItem, TableExtractionResult


# Pattern for an item anchor: standalone integer followed by a dot.
_ITEM_NUMBER = re.compile(r"^\s*(\d+)\s*\.\s*$")

# Decimal with comma (European format) — supports space thousands separator
# like "2 053,73". Anchored at full-line start/end so it only matches when
# the line is *just* a number (won't match "12\"Marble ..." or similar).
_DECIMAL = re.compile(r"^\s*(\d{1,3}(?:[\s.]?\d{3})*,\d{2})\s*$")

# VAT percent value, e.g. "10%", "18 %".
_VAT_PERCENT = re.compile(r"^\s*(\d+(?:[,.]\d+)?\s*%)\s*$")

# Unit of measure — filler line we don't emit but do skip.
_UM = re.compile(r"^\s*(each|pcs|pc|unit|kg|g|mtr|m|ml|l)\s*$", re.IGNORECASE)


class SpatialTableExtractor(BaseTableExtractor):
    """Line-item extractor using spatial clustering of OCR bboxes."""

    @property
    def extractor_name(self) -> str:
        return "spatial"

    def extract(self, ocr_result: OCRResult) -> TableExtractionResult:
        start = time.perf_counter()

        items_top_y = _find_anchor_y(ocr_result.lines, ITEMS_START_VARIANTS)
        summary_top_y = _find_anchor_y(ocr_result.lines, SUMMARY_START_VARIANTS)

        if items_top_y is None:
            return _empty(self.extractor_name, start, {"reason": "no ITEMS anchor"})

        bottom_y = (
            float(summary_top_y)
            if summary_top_y is not None
            else float(ocr_result.page.height)
        )

        # Region lines (indices preserved for precise anchor exclusion).
        region = [
            (i, line)
            for i, line in enumerate(ocr_result.lines)
            if items_top_y < line.bbox.y0 < bottom_y
        ]

        # Detect item anchor lines.
        anchors: list[tuple[int, Line, int]] = []
        for idx, line in region:
            m = _ITEM_NUMBER.match(line.text)
            if m:
                anchors.append((idx, line, int(m.group(1))))
        anchors.sort(key=lambda a: a[1].bbox.y0)

        if not anchors:
            return _empty(
                self.extractor_name,
                start,
                {
                    "reason": "no item anchors",
                    "items_top_y": items_top_y,
                    "summary_top_y": summary_top_y,
                },
            )

        items: list[InvoiceItem] = []
        for i, (anchor_idx, anchor_line, _item_no) in enumerate(anchors):
            if i + 1 < len(anchors):
                next_anchor = anchors[i + 1][1]
                next_line_h = max(1.0, next_anchor.bbox.y1 - next_anchor.bbox.y0)
                next_y_tol = max(4.0, next_line_h * 0.4)
                # Stop current item's continuation at the TOP of the next
                # anchor's band, not at its y0 — OCR sometimes places the
                # next item's description-line-1 at y0 slightly less than
                # the next anchor's y0, causing it to bleed into the current
                # item if we used the anchor's y0 directly.
                next_anchor_y = next_anchor.bbox.y0 - next_y_tol
            else:
                next_anchor_y = bottom_y
            item = self._build_item(
                region=region,
                anchor_idx=anchor_idx,
                anchor_line=anchor_line,
                next_anchor_y=next_anchor_y,
                page_width=float(ocr_result.page.width),
            )
            items.append(item)

        duration_ms = (time.perf_counter() - start) * 1000.0
        return TableExtractionResult(
            items=items,
            extractor=self.extractor_name,
            duration_ms=duration_ms,
            diagnostics={
                "items_top_y": items_top_y,
                "summary_top_y": summary_top_y,
                "anchor_count": len(anchors),
            },
        )

    # ----- per-item helpers -------------------------------------------------

    def _build_item(
        self,
        *,
        region: list[tuple[int, Line]],
        anchor_idx: int,
        anchor_line: Line,
        next_anchor_y: float,
        page_width: float,
    ) -> InvoiceItem:
        anchor_y0 = anchor_line.bbox.y0
        anchor_y1 = anchor_line.bbox.y1
        line_h = max(1.0, anchor_y1 - anchor_y0)
        # Band hugs the anchor's TOP edge tightly so description continuation
        # lines (which start below anchor_y1) are not absorbed into the band.
        # A wider 0.7*line_h tolerance reached ~60 px on a 25-px line and
        # caught the first continuation row on dense katanaml-style tables.
        y_tol = max(4.0, line_h * 0.4)
        band_top = anchor_y0 - y_tol
        band_bot = anchor_y0 + y_tol

        # 1. Same-y-band lines (exclude anchor itself)
        band_lines = [
            line
            for idx, line in region
            if idx != anchor_idx and band_top <= line.bbox.y0 <= band_bot
        ]

        # 2. Classify band lines by value pattern
        decimals: list[tuple[float, str]] = []  # (x, value)
        vat: str | None = None
        desc_line_1: Line | None = None

        for line in band_lines:
            text = line.text.strip()
            if _DECIMAL.match(text):
                decimals.append((line.bbox.x0, _DECIMAL.match(text).group(1)))
                continue
            if _VAT_PERCENT.match(text):
                if vat is None:  # first one wins
                    vat = _VAT_PERCENT.match(text).group(1).replace(" ", "")
                continue
            if _UM.match(text):
                continue  # filler — skip
            # candidate for description line 1: text to the right of the anchor
            if line.bbox.x0 >= anchor_line.bbox.x1:
                if desc_line_1 is None or line.bbox.x0 < desc_line_1.bbox.x0:
                    desc_line_1 = line

        decimals.sort(key=lambda pair: pair[0])
        qty = decimals[0][1] if len(decimals) >= 1 else None
        net_price = decimals[1][1] if len(decimals) >= 2 else None
        net_worth = decimals[2][1] if len(decimals) >= 3 else None
        gross_worth = decimals[3][1] if len(decimals) >= 4 else None

        # 3. Description — line 1 from the anchor band + continuation lines
        desc_parts: list[str] = []
        if desc_line_1 is not None:
            desc_parts.append(desc_line_1.text.strip())

        desc_left = (
            desc_line_1.bbox.x0 if desc_line_1 is not None else anchor_line.bbox.x1 + 10
        )
        desc_right = (
            decimals[0][0] - 10 if decimals else page_width / 3.0
        )

        for idx, line in region:
            if idx == anchor_idx:
                continue
            if line.bbox.y0 <= band_bot:
                continue
            if line.bbox.y0 >= next_anchor_y:
                continue
            if line.bbox.x0 < desc_left - 20:
                continue
            if line.bbox.x0 >= desc_right:
                continue
            desc_parts.append(line.text.strip())

        if desc_parts:
            desc_raw = " ".join(p for p in desc_parts if p)
            # Apply the same space-reinsertion normaliser we use on
            # seller/client fields — OCR collapses spaces the same way
            # inside item descriptions (see progress.md 2026-04-18 lift
            # from 0.000 to ~0.55 on seller/client F1).
            desc: str | None = normalize_multiword_spacing(desc_raw)
        else:
            desc = None

        return InvoiceItem(
            item_desc=desc,
            item_qty=qty,
            item_net_price=net_price,
            item_net_worth=net_worth,
            item_vat=vat,
            item_gross_worth=gross_worth,
        )


# ----- module-level helpers -------------------------------------------------


def _find_anchor_y(lines: list[Line], variants: list[str]) -> float | None:
    """Return the y0 of the first line that matches any of ``variants`` standalone."""
    for line in lines:
        if matches_variant(line.text, variants):
            return line.bbox.y0
    return None


def _empty(extractor_name: str, start: float, diagnostics: dict) -> TableExtractionResult:
    return TableExtractionResult(
        items=[],
        extractor=extractor_name,
        duration_ms=(time.perf_counter() - start) * 1000.0,
        diagnostics=diagnostics,
    )
