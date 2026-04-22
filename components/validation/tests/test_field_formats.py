"""Tests for the field-format validators."""

import pytest

from components.validation.rules.field_formats import (
    validate_client_tax_id,
    validate_iban_shape,
    validate_invoice_date,
    validate_invoice_no,
    validate_seller_tax_id,
)
from components.validation.types import RuleOutcome

from ._fixtures import make_extraction


class TestInvoiceNo:
    def test_valid(self):
        f = validate_invoice_no(make_extraction(invoice_no="97159829"))
        assert f.outcome == RuleOutcome.PASS

    @pytest.mark.parametrize("bad", ["abc", "123", "12345678901"])  # too short / non-digit / too long
    def test_invalid(self, bad):
        f = validate_invoice_no(make_extraction(invoice_no=bad))
        assert f.outcome == RuleOutcome.FAIL

    def test_missing_is_not_applicable(self):
        f = validate_invoice_no(make_extraction(invoice_no=None))
        assert f.outcome == RuleOutcome.NOT_APPLICABLE


class TestInvoiceDate:
    def test_valid(self):
        f = validate_invoice_date(make_extraction(invoice_date="09/18/2015"))
        assert f.outcome == RuleOutcome.PASS

    @pytest.mark.parametrize(
        "bad",
        [
            "2015-09-18",     # ISO-8601 — not the katanaml convention
            "18/09/2015",     # DD/MM/YYYY — wrong month/day order for an actual month
            "9/18",           # incomplete
            "garbage",
        ],
    )
    def test_invalid(self, bad):
        f = validate_invoice_date(make_extraction(invoice_date=bad))
        assert f.outcome == RuleOutcome.FAIL

    def test_missing_is_not_applicable(self):
        f = validate_invoice_date(make_extraction(invoice_date=None))
        assert f.outcome == RuleOutcome.NOT_APPLICABLE


class TestSellerTaxId:
    def test_valid(self):
        f = validate_seller_tax_id(make_extraction(seller_tax_id="985-73-8194"))
        assert f.outcome == RuleOutcome.PASS

    def test_invalid(self):
        f = validate_seller_tax_id(make_extraction(seller_tax_id="985738194"))
        assert f.outcome == RuleOutcome.FAIL

    def test_missing_is_not_applicable(self):
        f = validate_seller_tax_id(make_extraction(seller_tax_id=None))
        assert f.outcome == RuleOutcome.NOT_APPLICABLE


class TestClientTaxId:
    def test_valid(self):
        f = validate_client_tax_id(make_extraction(client_tax_id="994-72-1270"))
        assert f.outcome == RuleOutcome.PASS

    def test_invalid(self):
        f = validate_client_tax_id(make_extraction(client_tax_id="abc-de-fghi"))
        assert f.outcome == RuleOutcome.FAIL


class TestIbanShape:
    def test_valid(self):
        f = validate_iban_shape(make_extraction(iban="GB82WEST12345698765432"))
        assert f.outcome == RuleOutcome.PASS

    def test_accepts_iban_with_spaces(self):
        f = validate_iban_shape(make_extraction(iban="GB82 WEST 1234 5698 7654 32"))
        assert f.outcome == RuleOutcome.PASS

    @pytest.mark.parametrize("bad", ["GB", "GB82", "82GBWEST12345698765432", "not_iban"])
    def test_invalid_shape(self, bad):
        f = validate_iban_shape(make_extraction(iban=bad))
        assert f.outcome == RuleOutcome.FAIL

    def test_missing_is_not_applicable(self):
        f = validate_iban_shape(make_extraction(iban=None))
        assert f.outcome == RuleOutcome.NOT_APPLICABLE
