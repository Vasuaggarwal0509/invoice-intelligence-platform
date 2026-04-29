"""Tests for ValidationEngine (end-to-end over the rule modules)."""

import pytest

from extraction_layer.components.validation.engine import ValidationEngine
from extraction_layer.components.validation.types import RuleOutcome, ValidationResult

from ._fixtures import make_extraction, make_item, make_tables


@pytest.fixture
def engine():
    return ValidationEngine()


class TestSingleInvoiceValidation:
    def test_clean_invoice_all_pass(self, engine):
        result = engine.validate(make_extraction(), make_tables())
        assert isinstance(result, ValidationResult)
        assert result.all_checks_pass()
        # 6 single-field rules + 2 rules * 1 item = 8 findings.
        assert len(result.findings) == 8

    def test_rule_names_present(self, engine):
        result = engine.validate(make_extraction(), make_tables())
        rule_names = {f.rule_name for f in result.findings}
        assert {
            "invoice_no_format",
            "invoice_date_format",
            "tax_id_format",
            "iban_shape",
            "iban_checksum",
            "item_net_worth_consistency",
            "item_gross_worth_consistency",
        }.issubset(rule_names)

    def test_bad_iban_triggers_checksum_fail(self, engine):
        # Deterministically invalid IBAN — check digits flipped. Using a
        # definitively-broken IBAN (not an OCR-derived one) because mod-97
        # is only ~96% effective; some OCR errors coincidentally produce
        # valid checksums (documented in test_iban_checksum.py).
        result = engine.validate(
            make_extraction(iban="GB00WEST12345698765432"),
            make_tables(),
        )
        failures = result.failures()
        assert any(f.rule_name == "iban_checksum" for f in failures)

    def test_bad_item_arithmetic_triggers_fail(self, engine):
        result = engine.validate(
            make_extraction(),
            make_tables(
                items=[
                    make_item(
                        qty="2,00", net_price="10,00", net_worth="99,00", gross_worth="108,90"
                    ),
                ]
            ),
        )
        failures = result.failures()
        assert any(f.rule_name == "item_net_worth_consistency" for f in failures)

    def test_no_tables_skips_item_rules(self, engine):
        result = engine.validate(make_extraction(), tables=None)
        rule_names = {f.rule_name for f in result.findings}
        assert "item_net_worth_consistency" not in rule_names
        assert "item_gross_worth_consistency" not in rule_names

    def test_missing_fields_degrade_to_not_applicable(self, engine):
        extraction = make_extraction(
            invoice_no=None,
            invoice_date=None,
            iban=None,
            seller_tax_id=None,
            client_tax_id=None,
        )
        result = engine.validate(extraction, tables=None)
        assert result.all_checks_pass()  # missing != failure
        assert result.not_applicable_count() == 6


class TestBatchValidation:
    def test_batch_adds_duplicate_rule(self, engine):
        batch = [make_extraction(invoice_no="1"), make_extraction(invoice_no="2")]
        tables_list = [make_tables(), make_tables()]
        results = engine.validate_batch(batch, tables_list)
        assert len(results) == 2
        for r in results:
            rule_names = {f.rule_name for f in r.findings}
            assert "batch_duplicate" in rule_names

    def test_batch_detects_duplicate(self, engine):
        dup = make_extraction(invoice_no="77")
        batch = [dup, dup]
        results = engine.validate_batch(batch, [make_tables(), make_tables()])
        for r in results:
            dup_findings = [f for f in r.findings if f.rule_name == "batch_duplicate"]
            assert len(dup_findings) == 1
            assert dup_findings[0].outcome == RuleOutcome.FAIL

    def test_batch_without_tables_list(self, engine):
        # tables_list parameter is optional — test the default path.
        batch = [make_extraction(invoice_no="1"), make_extraction(invoice_no="2")]
        results = engine.validate_batch(batch)
        assert len(results) == 2

    def test_mismatched_batch_lengths_raises(self, engine):
        batch = [make_extraction(invoice_no="1")]
        with pytest.raises(ValueError):
            engine.validate_batch(batch, tables_list=[make_tables(), make_tables()])
