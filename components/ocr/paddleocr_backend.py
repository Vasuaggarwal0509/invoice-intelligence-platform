"""
PaddleOCR-direct backend — SCAFFOLDED, not implemented.

This backend exists as the escalation path if our default RapidOCR backend
cannot cover some feature of the latest PaddleOCR stack. The most likely
reason to enable it is **PP-StructureV3 for invoice tables** (see
`research.md` §3.5 and `project.md` §2.4).

To enable:
  1. Install:
       pip install -e ".[paddleocr]"
     (pulls ``paddleocr`` plus its PaddlePaddle runtime; expect a larger
      install footprint than RapidOCR, and version-specific quirks —
      see PaddleOCR GitHub issues #11560, #16100, #16484 referenced in
      research.md for the kind of trouble this brings.)
  2. Implement ``ocr()`` to run ``paddleocr.PaddleOCR(...)`` and map the
     output to our shared OCRResult schema.
  3. If using PP-StructureV3, consider using this backend ONLY for the
     table sub-component, not for full-page OCR (per the research
     conclusion: "scope this backend to what RapidOCR cannot do").
  4. Remove this notice.
"""

from typing import Any

from .base import BaseOCR, ImageInput
from .types import OCRResult


class PaddleOCRBackend(BaseOCR):
    """Scaffold for a PaddleOCR-direct backend. Not yet implemented."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    @property
    def backend_name(self) -> str:
        return "paddleocr"

    def ocr(self, image: ImageInput) -> OCRResult:
        raise NotImplementedError(
            "PaddleOCRBackend is scaffolded but not implemented at prototype time. "
            "See components/ocr/paddleocr_backend.py for enablement steps."
        )
