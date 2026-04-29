"""Synthetic OCR fixtures that mirror the 2026-04-18 spot-check layout.

Avoids loading real OCR models in unit tests — these fixtures are small,
deterministic, and reproduce the OCR quirks (label concatenation,
digit-letter substitution, multi-line addresses) documented in
`progress.md`.
"""

from extraction_layer.components.ocr.types import BoundingBox, Line, OCRResult, PageSize


def make_line(
    text: str, x0: float, y0: float, x1: float, y1: float, confidence: float = 0.95
) -> Line:
    return Line(
        text=text,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        polygon=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        tokens=[],
        confidence=confidence,
    )


def sample00_like_ocr() -> OCRResult:
    """An OCRResult shaped like sample 00 from the 2026-04-18 spot-check.

    Left column has "Seller:" anchored at x≈100, right column "Client:"
    at x≈450. Tax ids and IBAN follow the spot-check's OCR-quirk forms
    (label concatenation).
    """
    lines = [
        make_line("Invoice no: 97159829", 100, 100, 400, 130),
        make_line("Date of issue:", 100, 150, 250, 180),
        make_line("09/18/2015", 400, 150, 500, 180),
        make_line("Seller:", 100, 250, 200, 280),
        make_line("Client:", 450, 250, 550, 280),
        make_line("Bradley-Andrade", 100, 290, 300, 320),
        make_line("Castro PLC", 450, 290, 580, 320),
        make_line("9879 Elizabeth Common", 100, 330, 320, 360),
        make_line("Unit 9678 Box 9664", 450, 330, 620, 360),
        make_line("Lake Jonathan, RI 12335", 100, 370, 370, 400),
        make_line("DPO AP 69387", 450, 370, 580, 400),
        make_line("Taxld:985-73-8194", 100, 450, 330, 480),
        make_line("Taxld:994-72-1270", 450, 450, 680, 480),
        make_line("IBAN:GB81LZWO32519172531418", 100, 490, 500, 520),
        make_line("ITEMS", 100, 600, 200, 630),
    ]
    return OCRResult(
        tokens=[],
        lines=lines,
        page=PageSize(width=800, height=1000),
        backend="synthetic",
        duration_ms=0.0,
    )


def sample04_like_ocr() -> OCRResult:
    """Shaped like sample 04 — same layout, cleaner Invoice no spacing."""
    lines = [
        make_line("Invoice no: 16662010", 100, 100, 400, 130),
        make_line("Date of issue:", 100, 150, 250, 180),
        make_line("08/28/2016", 400, 150, 500, 180),
        make_line("Seller:", 100, 250, 200, 280),
        make_line("Client:", 450, 250, 550, 280),
        make_line("Smith-Cook", 100, 290, 300, 320),
        make_line("Snyder-Johnson", 450, 290, 580, 320),
        make_line("174 Justin Causeway", 100, 330, 320, 360),
        make_line("05173 Heather Mill", 450, 330, 620, 360),
        make_line("West Michaelmouth, ME 69894", 100, 370, 370, 400),
        make_line("Jenniferfort, WV79662", 450, 370, 580, 400),
        make_line("Tax Id:959-84-2124", 100, 450, 330, 480),
        make_line("Tax Id:938-85-4960", 450, 450, 680, 480),
        make_line("IBAN:GB20BAKH22085364527355", 100, 490, 500, 520),
        make_line("ITEMS", 100, 600, 200, 630),
    ]
    return OCRResult(
        tokens=[],
        lines=lines,
        page=PageSize(width=800, height=1000),
        backend="synthetic",
        duration_ms=0.0,
    )
