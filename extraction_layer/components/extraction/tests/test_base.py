"""Tests for BaseExtractor interface and the factory."""

import pytest

from extraction_layer.components.extraction import available_extractors, make_extractor
from extraction_layer.components.extraction.base import BaseExtractor


def test_baseextractor_is_abstract():
    with pytest.raises(TypeError):
        BaseExtractor()  # type: ignore[abstract]


def test_subclass_missing_abstract_cannot_instantiate():
    class Missing(BaseExtractor):
        @property
        def extractor_name(self) -> str:
            return "x"

    with pytest.raises(TypeError):
        Missing()  # type: ignore[abstract]


class TestFactory:
    def test_available_extractors_includes_expected(self):
        names = available_extractors()
        assert "heuristic" in names
        assert "layoutlmv3" in names

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            make_extractor("no-such-extractor")

    def test_make_heuristic(self):
        ext = make_extractor("heuristic")
        assert isinstance(ext, BaseExtractor)
        assert ext.extractor_name == "heuristic"

    def test_make_layoutlmv3_scaffold_instantiates(self):
        # Scaffolded backend must instantiate without errors.
        ext = make_extractor("layoutlmv3")
        assert isinstance(ext, BaseExtractor)
        assert ext.extractor_name == "layoutlmv3"
