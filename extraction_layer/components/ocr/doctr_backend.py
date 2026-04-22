"""
docTR backend — SCAFFOLDED, not implemented.

docTR (by Mindee) is included in the repo as a third comparator for future
benchmarking (see `research.md` §3.3). It is strong on structured English /
French documents but has thinner multilingual support than PaddleOCR-family
engines, so it is lower-priority than RapidOCR and Tesseract for our use case.

To enable:
  1. Install:
       pip install -e ".[doctr]"
     (pulls ``python-doctr`` and a Torch backend; GPU optional.)
  2. Implement ``ocr()`` to run docTR's predictor and map its output to our
     shared OCRResult schema.
  3. Remove this notice.
"""

from typing import Any

from .base import BaseOCR, ImageInput
from .types import OCRResult


class DocTRBackend(BaseOCR):
    """Scaffold for a docTR OCR backend. Not yet implemented."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    @property
    def backend_name(self) -> str:
        return "doctr"

    def ocr(self, image: ImageInput) -> OCRResult:
        raise NotImplementedError(
            "DocTRBackend is scaffolded but not implemented at prototype time. "
            "See components/ocr/doctr_backend.py for enablement steps."
        )
