"""Tests for the address-spacing normaliser."""

import pytest

from extraction_layer.components.extraction.heuristic.normalizers import normalize_address_spacing


class TestLowerToUpper:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("9879ElizabethCommon", "9879 Elizabeth Common"),
            ("ElizabethCommon", "Elizabeth Common"),
            ("SomeCamelCaseWord", "Some Camel Case Word"),
        ],
    )
    def test_splits_at_lower_to_upper(self, inp, expected):
        assert normalize_address_spacing(inp) == expected


class TestDigitToUpper:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("9879Elizabeth", "9879 Elizabeth"),
            ("123ABC", "123 ABC"),
        ],
    )
    def test_splits_at_digit_to_upper(self, inp, expected):
        assert normalize_address_spacing(inp) == expected


class TestLowerToDigit:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("Unit9678", "Unit 9678"),
            ("Box9664", "Box 9664"),
            ("Suite606", "Suite 606"),
        ],
    )
    def test_splits_at_lower_to_digit(self, inp, expected):
        assert normalize_address_spacing(inp) == expected


class TestPunctuationSpacing:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("Lake Jonathan,RI 12335", "Lake Jonathan, RI 12335"),
            ("Stacy VilleApt.488", "Stacy Ville Apt. 488"),
            ("foo,bar", "foo, bar"),
            ("hello.world", "hello. world"),
        ],
    )
    def test_inserts_space_after_punctuation(self, inp, expected):
        assert normalize_address_spacing(inp) == expected


class TestDoesNotOverSplit:
    @pytest.mark.parametrize(
        "inp",
        [
            "Castro PLC",  # acronym, stays
            "Smith-Cook",  # hyphenated, stays
            "9879 Elizabeth Common",  # already correct, stays
            "Lake Jonathan, RI 12335",  # already correct, stays
            "Bradley-Andrade",  # hyphenated name, stays
        ],
    )
    def test_already_correct_is_unchanged(self, inp):
        assert normalize_address_spacing(inp) == inp


class TestUppercaseRunsNotSplit:
    """Known limitation — uppercase-only sequences are left as-is."""

    @pytest.mark.parametrize(
        "inp",
        [
            "WV79662",  # state+zip that GT sometimes keeps joined
            "AA81651",  # same pattern, but GT separates — can't tell
        ],
    )
    def test_uppercase_followed_by_digit_not_split(self, inp):
        # Rule only splits lower->digit, not upper->digit.
        assert normalize_address_spacing(inp) == inp

    def test_uppercase_run_before_digit_splits_only_at_digit(self):
        # "DPOAP69387" -> "DPOAP 69387": digit preceded by uppercase still
        # gets a space because of the digit->upper rule (reverse direction).
        # Wait — actually this is digit *following* uppercase, which is
        # upper->digit. Our rule only handles lower->digit, so no split here.
        assert normalize_address_spacing("DPOAP69387") == "DPOAP69387"


class TestEndToEndExamples:
    """Mirrors the actual failure entries from the 2026-04-18 report."""

    def test_sample_00_seller_partial_fix(self):
        # The "Rl"/"RI" character confusion is not our concern here — that's
        # an OCR-level error. The normaliser only fixes spacing.
        raw = "Bradley-Andrade 9879ElizabethCommon Lake Jonathan,Rl 12335"
        expected = "Bradley-Andrade 9879 Elizabeth Common Lake Jonathan, Rl 12335"
        assert normalize_address_spacing(raw) == expected

    def test_sample_07_seller_comma_spacing(self):
        raw = "Gregory,Patterson and Fischer 439Hunter Land South Jameschester, MT 09091"
        expected = "Gregory, Patterson and Fischer 439 Hunter Land South Jameschester, MT 09091"
        assert normalize_address_spacing(raw) == expected

    def test_sample_03_seller_apt_dot_spacing(self):
        raw = "Nichols-Barajas 3882StacyVilleApt.488 Lake Kristinatown,ND 48049"
        expected = "Nichols-Barajas 3882 Stacy Ville Apt. 488 Lake Kristinatown, ND 48049"
        assert normalize_address_spacing(raw) == expected


class TestEdgeCases:
    def test_empty_string(self):
        assert normalize_address_spacing("") == ""

    def test_already_spaced_not_double_spaced(self):
        # If the rule fires and adjacent text already had a space, no double.
        assert "  " not in normalize_address_spacing("Smith Cook 123 Main")

    def test_collapses_multiple_spaces(self):
        assert normalize_address_spacing("a  b   c") == "a b c"
