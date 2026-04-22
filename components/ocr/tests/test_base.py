"""Tests for the BaseOCR abstract interface and the factory."""

import pytest

from components.ocr import available_backends, make_ocr
from components.ocr.base import BaseOCR
from components.ocr.types import OCRResult


def test_baseocr_is_abstract():
    with pytest.raises(TypeError):
        BaseOCR()  # type: ignore[abstract]


def test_concrete_must_implement_ocr():
    class MissingOCR(BaseOCR):
        @property
        def backend_name(self) -> str:
            return "missing_ocr"

    with pytest.raises(TypeError):
        MissingOCR()  # type: ignore[abstract]


def test_concrete_must_implement_backend_name():
    class MissingName(BaseOCR):
        def ocr(self, image):  # type: ignore[override]
            raise NotImplementedError

    with pytest.raises(TypeError):
        MissingName()  # type: ignore[abstract]


def test_fully_implemented_subclass_can_instantiate():
    class DummyOCR(BaseOCR):
        @property
        def backend_name(self) -> str:
            return "dummy"

        def ocr(self, image) -> OCRResult:  # type: ignore[override]
            raise NotImplementedError

    instance = DummyOCR()
    assert instance.backend_name == "dummy"
    assert "dummy" in repr(instance)


def test_warmup_is_noop_by_default():
    class DummyOCR(BaseOCR):
        @property
        def backend_name(self) -> str:
            return "dummy"

        def ocr(self, image) -> OCRResult:  # type: ignore[override]
            raise NotImplementedError

    # Default warmup must not raise.
    DummyOCR().warmup()


class TestFactory:
    def test_available_backends_includes_expected(self):
        names = available_backends()
        assert "rapidocr" in names
        assert "tesseract" in names
        assert "paddleocr" in names
        assert "doctr" in names

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError):
            make_ocr("no-such-backend")

    def test_make_scaffolded_backends(self):
        # Scaffolded backends must instantiate without any heavy dependency.
        for name in ("tesseract", "paddleocr", "doctr"):
            backend = make_ocr(name)
            assert isinstance(backend, BaseOCR)
            assert backend.backend_name == name
