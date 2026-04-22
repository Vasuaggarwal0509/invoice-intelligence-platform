"""Tests for BaseTableExtractor and the factory."""

import pytest

from components.tables import available_table_extractors, make_table_extractor
from components.tables.base import BaseTableExtractor


def test_basetable_is_abstract():
    with pytest.raises(TypeError):
        BaseTableExtractor()  # type: ignore[abstract]


def test_subclass_missing_abstract_cannot_instantiate():
    class Missing(BaseTableExtractor):
        @property
        def extractor_name(self) -> str:
            return "x"

    with pytest.raises(TypeError):
        Missing()  # type: ignore[abstract]


class TestFactory:
    def test_available_includes_expected(self):
        names = available_table_extractors()
        assert "spatial" in names
        assert "pp_structure" in names
        assert "layoutlm" in names

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            make_table_extractor("no-such")

    def test_make_spatial(self):
        ext = make_table_extractor("spatial")
        assert isinstance(ext, BaseTableExtractor)
        assert ext.extractor_name == "spatial"

    def test_make_pp_structure_scaffold(self):
        ext = make_table_extractor("pp_structure")
        assert ext.extractor_name == "pp_structure"

    def test_make_layoutlm_scaffold(self):
        ext = make_table_extractor("layoutlm")
        assert ext.extractor_name == "layoutlm"
