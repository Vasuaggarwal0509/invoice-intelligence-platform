"""Synthetic OCRResults for table-extraction tests.

Coordinates are simplified (small integer grid, not the 2481x3508 of real
katanaml invoices) so tests stay fast and readable. The structural
patterns — ITEMS/SUMMARY anchors, item-number column, decimal columns,
description wrapping — match what OCR produces on actual invoices.
"""

from extraction_layer.components.ocr.types import BoundingBox, Line, OCRResult, PageSize

# Reference column x-ranges for the fixtures:
# No.          : x=100-130
# Description  : x=150-300
# Qty          : x=350-400
# UM           : x=430-470
# Net price    : x=500-570
# Net worth    : x=600-670
# VAT %        : x=700-740
# Gross worth  : x=770-840


def _line(text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 0.95) -> Line:
    return Line(
        text=text,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        polygon=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        tokens=[],
        confidence=conf,
    )


def _page(lines: list[Line], width: int = 900, height: int = 1200) -> OCRResult:
    return OCRResult(
        tokens=[],
        lines=lines,
        page=PageSize(width=width, height=height),
        backend="synthetic",
        duration_ms=0.0,
    )


def one_item_with_3line_description() -> OCRResult:
    """One item whose description wraps over three lines (sample 00 style)."""
    lines = [
        _line("ITEMS", 100, 100, 200, 125),
        # Header row (fairly approximate positions)
        _line("No.", 100, 150, 130, 175),
        _line("Description", 150, 150, 300, 175),
        _line("Qty", 350, 150, 400, 175),
        _line("UM", 430, 150, 470, 175),
        _line("Net price", 500, 150, 570, 175),
        _line("Net worth", 600, 150, 670, 175),
        _line("VAT[%]", 700, 150, 740, 175),
        _line("Gross worth", 770, 150, 840, 175),
        # Item 1 row (description line 1 is on the same y-band)
        _line("1.", 100, 220, 130, 245),
        _line("Marble Lapis Inlay Chess", 150, 220, 300, 245),
        _line("2,00", 350, 220, 400, 245),
        _line("each", 430, 220, 470, 245),
        _line("444,60", 500, 220, 570, 245),
        _line("889,20", 600, 220, 670, 245),
        _line("10%", 700, 220, 740, 245),
        _line("978,12", 770, 220, 840, 245),
        # Item 1 description continuations (below anchor band, above SUMMARY)
        _line("Table Top With 2 Pieces", 150, 260, 300, 285),
        _line("Wooden Stand W537", 150, 295, 290, 320),
        # Summary
        _line("SUMMARY", 100, 400, 200, 425),
    ]
    return _page(lines)


def three_items_single_line() -> OCRResult:
    """Three items, each with a one-line description (sample 04 style, simplified)."""
    lines = [
        _line("ITEMS", 100, 100, 200, 125),
        _line("No.", 100, 150, 130, 175),
        _line("Description", 150, 150, 300, 175),
        _line("Qty", 350, 150, 400, 175),
        _line("UM", 430, 150, 470, 175),
        _line("Net price", 500, 150, 570, 175),
        _line("Net worth", 600, 150, 670, 175),
        _line("VAT[%]", 700, 150, 740, 175),
        _line("Gross worth", 770, 150, 840, 175),
        # Item 1
        _line("1.", 100, 220, 130, 245),
        _line("Nintendo Gameboy", 150, 220, 300, 245),
        _line("1,00", 350, 220, 400, 245),
        _line("each", 430, 220, 470, 245),
        _line("65,00", 500, 220, 570, 245),
        _line("65,00", 600, 220, 670, 245),
        _line("10%", 700, 220, 740, 245),
        _line("71,50", 770, 220, 840, 245),
        # Item 2 — mirrors katanaml GT convention (lowercase "Playstation",
        # not Sony-official "PlayStation") so the normaliser's lower->upper
        # rule does not split a proper noun in the fixture.
        _line("2.", 100, 290, 130, 315),
        _line("Sony Playstation 4", 150, 290, 300, 315),
        _line("3,00", 350, 290, 400, 315),
        _line("each", 430, 290, 470, 315),
        _line("399,99", 500, 290, 570, 315),
        _line("1199,97", 600, 290, 670, 315),
        _line("10%", 700, 290, 740, 315),
        _line("1319,97", 770, 290, 840, 315),
        # Item 3
        _line("3.", 100, 360, 130, 385),
        _line("Atari Flashback", 150, 360, 300, 385),
        _line("4,00", 350, 360, 400, 385),
        _line("each", 430, 360, 470, 385),
        _line("8,50", 500, 360, 570, 385),
        _line("34,00", 600, 360, 670, 385),
        _line("10%", 700, 360, 740, 385),
        _line("37,40", 770, 360, 840, 385),
        _line("SUMMARY", 100, 450, 200, 475),
    ]
    return _page(lines)


def no_items_anchor() -> OCRResult:
    """OCR output without an ITEMS anchor — extractor should return empty items."""
    lines = [
        _line("Invoice no: 1234", 100, 100, 300, 125),
        _line("some other text", 100, 150, 300, 175),
    ]
    return _page(lines)


def no_summary_anchor() -> OCRResult:
    """Items table with no SUMMARY anchor — extractor should use page bottom."""
    lines = [
        _line("ITEMS", 100, 100, 200, 125),
        _line("No.", 100, 150, 130, 175),
        _line("Description", 150, 150, 300, 175),
        _line("Qty", 350, 150, 400, 175),
        _line("UM", 430, 150, 470, 175),
        _line("Net price", 500, 150, 570, 175),
        _line("Net worth", 600, 150, 670, 175),
        _line("VAT[%]", 700, 150, 740, 175),
        _line("Gross worth", 770, 150, 840, 175),
        _line("1.", 100, 220, 130, 245),
        _line("Some item", 150, 220, 300, 245),
        _line("2,00", 350, 220, 400, 245),
        _line("each", 430, 220, 470, 245),
        _line("100,00", 500, 220, 570, 245),
        _line("200,00", 600, 220, 670, 245),
        _line("10%", 700, 220, 740, 245),
        _line("220,00", 770, 220, 840, 245),
    ]
    return _page(lines)
