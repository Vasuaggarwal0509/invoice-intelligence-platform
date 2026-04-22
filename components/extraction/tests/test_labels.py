"""Tests for label_is_label / line_contains_label fuzzy matchers."""

import pytest

from components.extraction.heuristic.labels import (
    LABEL_VARIANTS,
    line_contains_label,
    line_is_label,
)


class TestLineIsLabel:
    @pytest.mark.parametrize(
        "text,key",
        [
            ("Seller:", "seller"),
            ("Seller", "seller"),
            ("Client:", "client"),
            ("Client", "client"),
            ("ITEMS", "items_start"),
            ("Items", "items_start"),
            ("SUMMARY", "summary_start"),
        ],
    )
    def test_matches_standalone_label(self, text, key):
        assert line_is_label(text, key), f"expected {text!r} to match key {key!r}"

    @pytest.mark.parametrize(
        "text,key",
        [
            ("Seller: Bradley-Andrade 123 Main", "seller"),  # label+value too long
            ("Invoice no: 12345", "invoice_no"),             # has value
            ("Some random text", "seller"),
            ("", "seller"),
        ],
    )
    def test_rejects_label_plus_value_or_unrelated(self, text, key):
        assert not line_is_label(text, key), (
            f"expected {text!r} NOT to match key {key!r}"
        )


class TestLineContainsLabel:
    @pytest.mark.parametrize(
        "text,key",
        [
            ("Invoice no: 12345", "invoice_no"),
            ("Invoiceno:12345", "invoice_no"),
            ("Invoicen0:12345", "invoice_no"),       # o->0 OCR
            ("Tax Id: 985-73-8194", "tax_id"),
            ("Taxld:985-73-8194", "tax_id"),
            ("IBAN: GB81...", "iban"),
            ("Date of issue", "date"),
            ("Seller:", "seller"),
        ],
    )
    def test_detects_labels_in_lines(self, text, key):
        assert line_contains_label(text, key)

    def test_rejects_unrelated_text(self):
        assert not line_contains_label("random unrelated text", "invoice_no")
        assert not line_contains_label("Bradley-Andrade", "seller")  # name, not label

    def test_unknown_key_returns_false(self):
        assert not line_contains_label("anything", "no_such_key")


class TestLabelVariantsDictionary:
    def test_all_required_keys_present(self):
        required = {
            "seller",
            "client",
            "invoice_no",
            "date",
            "tax_id",
            "iban",
            "items_start",
        }
        assert required.issubset(LABEL_VARIANTS.keys())

    def test_no_empty_variant_list(self):
        for key, variants in LABEL_VARIANTS.items():
            assert len(variants) > 0, f"{key!r} has no variants"

    def test_variants_are_strings(self):
        for variants in LABEL_VARIANTS.values():
            for v in variants:
                assert isinstance(v, str) and v.strip() == v
