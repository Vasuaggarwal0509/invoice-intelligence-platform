"""OCR component — pipeline stage 4: image -> OCRResult.

Public surface:

    from extraction_layer.components.ocr import BaseOCR, InvoiceInput, OCRResult, make_ocr

    ocr = make_ocr("rapidocr")

    # Lenient, in-process form (tests, scripts):
    result = ocr.ocr("invoice.png")

    # Service-boundary form (explicit wire contract):
    result = ocr.ocr_invoice(InvoiceInput(
        id="sample-001",
        content_type="image/png",
        image_bytes=open("invoice.png", "rb").read(),
    ))

Downstream stages (extraction, tables, qr, validation) consume OCRResult and
never branch on the concrete backend. See README.md + schema/ for details.
"""

from .base import BaseOCR, ImageInput
from .factory import available_backends, make_ocr
from .types import (
    BoundingBox,
    ContentType,
    InvoiceInput,
    Line,
    OCRResult,
    PageSize,
    Polygon,
    Token,
)

__all__ = [
    "BaseOCR",
    "BoundingBox",
    "ContentType",
    "ImageInput",
    "InvoiceInput",
    "Line",
    "OCRResult",
    "PageSize",
    "Polygon",
    "Token",
    "available_backends",
    "make_ocr",
]
