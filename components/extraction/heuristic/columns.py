"""
Column detection for seller / client separation.

The 2026-04-18 spot-check showed katanaml invoices have a two-column header:
"Seller:" in the left column, "Client:" in the right column. Below each
anchor, a multi-line address block runs until the table header ("ITEMS").

This module provides `detect_columns()` that, given an OCRResult, returns:
  - the y-coordinate of "Seller:" / "Client:" anchor lines
  - the page-split x-coordinate separating left vs right column
  - the indices of OCR lines belonging to left / right / neither column

Downstream extraction rules use these indices to attribute tax IDs,
IBAN, and address text to the correct party.
"""

from dataclasses import dataclass

from components.ocr.types import Line, OCRResult

from .labels import line_is_label


@dataclass(frozen=True)
class ColumnLayout:
    """Discovered column layout for one OCRResult."""

    # y-coordinate of the "Seller:" anchor line (None if not found)
    seller_anchor_y: float | None
    # y-coordinate of the "Client:" anchor line (None if not found)
    client_anchor_y: float | None
    # y-coordinate where the items table begins (block end, None if absent)
    items_start_y: float | None
    # x-coordinate splitting left vs right column
    split_x: float
    # Indices into ocr_result.lines attributed to the left (seller) column
    left_indices: list[int]
    # Indices into ocr_result.lines attributed to the right (client) column
    right_indices: list[int]


def detect_columns(ocr_result: OCRResult) -> ColumnLayout:
    """Detect seller / client columns in an OCR'd invoice.

    Returns a :class:`ColumnLayout`. Fields that cannot be found are set
    to None (anchors) or empty list (line indices); callers decide how
    to handle missing anchors.
    """
    lines = ocr_result.lines

    seller_anchor_y = _find_anchor_y(lines, "seller")
    client_anchor_y = _find_anchor_y(lines, "client")
    items_start_y = _find_anchor_y(lines, "items_start")

    # Page midline — safe default if both anchors are missing.
    split_x = _choose_split_x(
        lines,
        seller_anchor_y,
        client_anchor_y,
        page_width=ocr_result.page.width,
    )

    # Determine the y-range that is "between the anchors and the items table".
    block_start_y = _safe_min(seller_anchor_y, client_anchor_y)
    block_end_y = items_start_y if items_start_y is not None else float("inf")

    left_indices: list[int] = []
    right_indices: list[int] = []
    if block_start_y is not None:
        for i, line in enumerate(lines):
            # Skip the anchor lines themselves.
            if seller_anchor_y is not None and line.bbox.y0 == seller_anchor_y and line_is_label(line.text, "seller"):
                continue
            if client_anchor_y is not None and line.bbox.y0 == client_anchor_y and line_is_label(line.text, "client"):
                continue
            # Line must be below the earliest anchor, and above items start.
            if line.bbox.y0 < block_start_y:
                continue
            if line.bbox.y0 >= block_end_y:
                continue
            if _line_center_x(line) < split_x:
                left_indices.append(i)
            else:
                right_indices.append(i)

    return ColumnLayout(
        seller_anchor_y=seller_anchor_y,
        client_anchor_y=client_anchor_y,
        items_start_y=items_start_y,
        split_x=split_x,
        left_indices=left_indices,
        right_indices=right_indices,
    )


# ----- internal helpers -----------------------------------------------------


def _find_anchor_y(lines: list[Line], label_key: str) -> float | None:
    """Return the y0 of the first line that matches label_key as a standalone label."""
    for line in lines:
        if line_is_label(line.text, label_key):
            return line.bbox.y0
    return None


def _safe_min(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _line_center_x(line: Line) -> float:
    return (line.bbox.x0 + line.bbox.x1) / 2.0


def _choose_split_x(
    lines: list[Line],
    seller_y: float | None,
    client_y: float | None,
    page_width: int,
) -> float:
    """Pick a split x based on the seller / client anchor centers if present.

    If both anchors are known, split at the midpoint of their centers. If
    only one is known, split at page-midline. Otherwise fall back to half
    the page width.
    """
    seller_cx: float | None = None
    client_cx: float | None = None
    for line in lines:
        if seller_y is not None and line.bbox.y0 == seller_y and line_is_label(line.text, "seller"):
            seller_cx = _line_center_x(line)
        if client_y is not None and line.bbox.y0 == client_y and line_is_label(line.text, "client"):
            client_cx = _line_center_x(line)

    if seller_cx is not None and client_cx is not None:
        return (seller_cx + client_cx) / 2.0
    return page_width / 2.0
