"""
Tesseract backend — SCAFFOLDED, not implemented.

Tesseract 5 is the intended fast-path alternative for clean-text PDFs where
latency matters more than raw accuracy. See `research.md` §3.3 for the
comparison; Tesseract is ~6x faster than PaddleOCR on clean text but weaker
on tables and photographic conditions.

To enable:
  1. Install the system binary:
       Ubuntu/Debian:  sudo apt-get install tesseract-ocr
       macOS:          brew install tesseract
       Windows:        https://github.com/UB-Mannheim/tesseract/wiki
  2. Install the Python wrapper:
       pip install -e ".[tesseract]"
  3. Replace the NotImplementedError raise in ``ocr()`` with a real
     implementation that returns an OCRResult matching the shared schema.
  4. Remove this notice.
"""

from typing import Any

from .base import BaseOCR, ImageInput
from .types import OCRResult


class TesseractBackend(BaseOCR):
    """Scaffold for a Tesseract 5 OCR backend. Not yet implemented."""

    def __init__(self, **_kwargs: Any) -> None:
        # Accepts kwargs for forward-compatibility with the interface.
        # No heavy imports until the backend is implemented.
        pass

    @property
    def backend_name(self) -> str:
        return "tesseract"

    def ocr(self, image: ImageInput) -> OCRResult:
        raise NotImplementedError(
            "TesseractBackend is scaffolded but not implemented at prototype time. "
            "See components/ocr/tesseract_backend.py for enablement steps."
        )
