"""Tests for the ISO 13616 IBAN checksum."""

import pytest

from extraction_layer.components.validation.rules.iban_checksum import iban_is_valid, validate_iban_checksum
from extraction_layer.components.validation.types import RuleOutcome

from ._fixtures import make_extraction


class TestIbanIsValid:
    # ECBS / Wikipedia canonical valid IBANs.
    VALID = [
        "GB82WEST12345698765432",     # UK
        "DE89370400440532013000",     # Germany
        "FR1420041010050500013M02606",  # France
        "NL91ABNA0417164300",         # Netherlands
    ]

    @pytest.mark.parametrize("iban", VALID)
    def test_canonical_valid_ibans(self, iban):
        assert iban_is_valid(iban) is True

    def test_with_spaces_is_valid(self):
        # Banks print IBANs with spaces for readability. Normalisation strips them.
        assert iban_is_valid("GB82 WEST 1234 5698 7654 32") is True

    @pytest.mark.parametrize(
        "iban",
        [
            "GB00WEST12345698765432",           # wrong check digits — deterministically invalid
            "GB83WEST12345698765432",           # check digits one off from valid GB82...
            "GB82WEST123456987654ZZ",           # wrong final chars
            "DE00370400440532013000",           # wrong check digits on valid DE IBAN
        ],
    )
    def test_invalid_ibans(self, iban):
        assert iban_is_valid(iban) is False

    # Known limitation: ISO 13616 mod-97 catches ~96% of single-character
    # corruptions but not all. Some OCR errors (especially multi-char
    # permutations) can coincidentally produce a valid checksum.
    # These IBANs came from our 2026-04-18 G1G2 eval — OCR corrupted them,
    # but the result happens to pass mod-97.
    @pytest.mark.parametrize(
        "iban_from_ocr_error",
        [
            "GB10YCPS61791374226282",           # sample 07: GT had extra "791" chunk; stripped version is coincidentally valid
            "GB31LZXS20242755934691",           # sample 01: S↔5 swap at position 8; coincidentally valid
        ],
    )
    def test_some_ocr_errors_pass_mod97_coincidentally(self, iban_from_ocr_error):
        # Document the false-negative class rather than pretend mod-97 is infallible.
        # Downstream validation should cross-check IBAN against vendor records or
        # bank-directory lookups when higher assurance is needed.
        assert iban_is_valid(iban_from_ocr_error) is True

    @pytest.mark.parametrize(
        "iban",
        [
            "",
            "GB",
            "GB82",
            "lowercase_nonsense",
            "GB82WEST!!1234",
        ],
    )
    def test_malformed_inputs(self, iban):
        assert iban_is_valid(iban) is False


class TestValidateIbanChecksumFinding:
    def test_valid_iban_returns_pass(self):
        extraction = make_extraction(iban="GB82WEST12345698765432")
        finding = validate_iban_checksum(extraction)
        assert finding.rule_name == "iban_checksum"
        assert finding.outcome == RuleOutcome.PASS

    def test_invalid_iban_returns_fail_with_reason(self):
        # Deterministically invalid — check digits flipped.
        extraction = make_extraction(iban="GB00WEST12345698765432")
        finding = validate_iban_checksum(extraction)
        assert finding.outcome == RuleOutcome.FAIL
        assert finding.reason is not None
        assert "mod-97" in finding.reason.lower()
        assert finding.observed == "GB00WEST12345698765432"

    def test_missing_iban_returns_not_applicable(self):
        extraction = make_extraction(iban=None)
        finding = validate_iban_checksum(extraction)
        assert finding.outcome == RuleOutcome.NOT_APPLICABLE
