"""Tests for the European decimal and percent parsers."""

from decimal import Decimal

import pytest

from extraction_layer.components.validation.parsers import parse_european_decimal, parse_percent


class TestParseEuropeanDecimal:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("2,00", Decimal("2.00")),
            ("889,20", Decimal("889.20")),
            ("1 319,97", Decimal("1319.97")),          # space thousands
            ("1.319,97", Decimal("1319.97")),          # dot thousands
            ("1 319.50,97", Decimal("131950.97")),     # mixed thousands separators
            ("10", Decimal("10")),                     # integer
            ("10.00", Decimal("10.00")),               # US format accepted because no comma
            ("0,00", Decimal("0.00")),
            ("-5,25", Decimal("-5.25")),
        ],
    )
    def test_valid_inputs(self, inp, expected):
        assert parse_european_decimal(inp) == expected

    @pytest.mark.parametrize(
        "inp",
        [None, "", "   ", "not a number", "abc,def", "12,,5"],
    )
    def test_invalid_returns_none(self, inp):
        assert parse_european_decimal(inp) is None


class TestParsePercent:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            ("10%", Decimal("10")),
            ("10 %", Decimal("10")),
            ("18%", Decimal("18")),
            ("10,5%", Decimal("10.5")),
            ("10", Decimal("10")),               # no % symbol
        ],
    )
    def test_valid(self, inp, expected):
        assert parse_percent(inp) == expected

    def test_invalid_returns_none(self):
        assert parse_percent(None) is None
        assert parse_percent("") is None
        assert parse_percent("bogus") is None
