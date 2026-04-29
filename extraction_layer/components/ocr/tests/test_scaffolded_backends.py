"""Tests that scaffolded OCR backends are importable but not runnable.

These tests exist so the "swap path is visible from day one" property from
`project.md` §8.0 is enforced by CI. If any scaffolded backend starts
needing heavy dependencies at import / __init__ time, these tests fail and
we correct the drift.
"""

import numpy as np
import pytest

from extraction_layer.components.ocr.base import BaseOCR
from extraction_layer.components.ocr.doctr_backend import DocTRBackend
from extraction_layer.components.ocr.paddleocr_backend import PaddleOCRBackend
from extraction_layer.components.ocr.tesseract_backend import TesseractBackend

SCAFFOLDED = [
    pytest.param(TesseractBackend, "tesseract", id="tesseract"),
    pytest.param(PaddleOCRBackend, "paddleocr", id="paddleocr"),
    pytest.param(DocTRBackend, "doctr", id="doctr"),
]


@pytest.mark.parametrize("backend_cls, expected_name", SCAFFOLDED)
def test_scaffolded_backend_instantiates(backend_cls, expected_name):
    # Instantiation must succeed without the underlying OCR library installed.
    instance = backend_cls()
    assert isinstance(instance, BaseOCR)
    assert instance.backend_name == expected_name


@pytest.mark.parametrize("backend_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_backend_accepts_forward_kwargs(backend_cls, _expected_name):
    # Constructor must accept arbitrary kwargs for forward compatibility.
    backend_cls(some_future_option=True, another=42)


@pytest.mark.parametrize("backend_cls, _expected_name", SCAFFOLDED)
def test_scaffolded_backend_raises_on_ocr(backend_cls, _expected_name):
    instance = backend_cls()
    img = np.full((64, 128, 3), 255, dtype=np.uint8)
    with pytest.raises(NotImplementedError):
        instance.ocr(img)
