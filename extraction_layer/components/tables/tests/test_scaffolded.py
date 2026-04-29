"""Tests that scaffolded table backends are importable but not runnable."""

import pytest

from extraction_layer.components.ocr.types import OCRResult, PageSize
from extraction_layer.components.tables.base import BaseTableExtractor
from extraction_layer.components.tables.layoutlm_backend import LayoutLMTableExtractor
from extraction_layer.components.tables.pp_structure_backend import PPStructureTableExtractor

SCAFFOLDED = [
    pytest.param(PPStructureTableExtractor, "pp_structure", id="pp_structure"),
    pytest.param(LayoutLMTableExtractor, "layoutlm", id="layoutlm"),
]


def _empty_ocr() -> OCRResult:
    return OCRResult(
        tokens=[],
        lines=[],
        page=PageSize(width=100, height=100),
        backend="synthetic",
        duration_ms=0.0,
    )


@pytest.mark.parametrize("cls,name", SCAFFOLDED)
def test_instantiates_without_heavy_deps(cls, name):
    ext = cls()
    assert isinstance(ext, BaseTableExtractor)
    assert ext.extractor_name == name


@pytest.mark.parametrize("cls,_name", SCAFFOLDED)
def test_accepts_forward_kwargs(cls, _name):
    cls(future_option=True)


@pytest.mark.parametrize("cls,_name", SCAFFOLDED)
def test_extract_raises_not_implemented(cls, _name):
    ext = cls()
    with pytest.raises(NotImplementedError):
        ext.extract(_empty_ocr())
