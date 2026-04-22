"""Tests for the G1 regex patterns against the OCR quirks in the spot-check."""

import pytest

from extraction_layer.components.extraction.heuristic.regex_patterns import (
    DATE_ANCHORED,
    DATE_BARE,
    IBAN_ANCHORED,
    IBAN_BARE,
    INVOICE_NO,
    INVOICE_NO_BARE,
    TAX_ID_ANCHORED,
    TAX_ID_BARE,
)


# ----- INVOICE_NO ----------------------------------------------------------


class TestInvoiceNoAnchored:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Invoice no: 97159829", "97159829"),
            ("Invoice no:97159829", "97159829"),
            ("Invoiceno:97159829", "97159829"),          # space-lost
            ("Invoiceno 97159829", "97159829"),
            ("Invoicen0:97159829", "97159829"),          # o -> 0 OCR error
            ("Invoice no. 12222347", "12222347"),
            ("invoice no: 123456", "123456"),            # lowercase
            ("INVOICE NO: 12345678", "12345678"),        # uppercase
        ],
    )
    def test_matches_variants(self, text, expected):
        m = INVOICE_NO.search(text)
        assert m is not None, f"INVOICE_NO did not match {text!r}"
        assert m.group("value") == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Nothing here",
            "Invoice: no number given",
            "invoiceno:",  # label with no digits
        ],
    )
    def test_does_not_match_non_invoice_text(self, text):
        assert INVOICE_NO.search(text) is None


class TestInvoiceNoBare:
    def test_matches_bare_numeric_line(self):
        m = INVOICE_NO_BARE.match("  12345678  ")
        assert m is not None
        assert m.group("value") == "12345678"

    def test_rejects_too_short(self):
        assert INVOICE_NO_BARE.match("1234") is None

    def test_rejects_with_surrounding_text(self):
        assert INVOICE_NO_BARE.match("no 12345678") is None


# ----- DATE ---------------------------------------------------------------


class TestDateAnchored:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Date of issue: 09/18/2015", "09/18/2015"),
            ("Date of issue:09/18/2015", "09/18/2015"),
            ("Invoice date: 01/02/2020", "01/02/2020"),
            ("Issue date 3/4/22", "3/4/22"),
            ("Date: 09-18-2015", "09-18-2015"),
        ],
    )
    def test_matches_variants(self, text, expected):
        m = DATE_ANCHORED.search(text)
        assert m is not None
        assert m.group("value") == expected


class TestDateBare:
    def test_matches_bare_date(self):
        m = DATE_BARE.match("09/18/2015")
        assert m is not None
        assert m.group("value") == "09/18/2015"

    def test_rejects_partial(self):
        assert DATE_BARE.match("not a date") is None


# ----- TAX_ID -------------------------------------------------------------


class TestTaxIdAnchored:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Tax Id: 985-73-8194", "985-73-8194"),
            ("Tax Id:985-73-8194", "985-73-8194"),
            ("Taxld:985-73-8194", "985-73-8194"),           # I -> l OCR
            ("Tax ld:985-73-8194", "985-73-8194"),          # I -> l with space
            ("TaxId:985-73-8194", "985-73-8194"),
            ("Tax 1d: 985-73-8194", "985-73-8194"),          # I -> 1 OCR
            ("TAX ID: 985-73-8194", "985-73-8194"),          # uppercase
        ],
    )
    def test_matches_variants(self, text, expected):
        m = TAX_ID_ANCHORED.search(text)
        assert m is not None, f"TAX_ID_ANCHORED did not match {text!r}"
        assert m.group("value") == expected


class TestTaxIdBare:
    def test_matches_bare_pattern(self):
        m = TAX_ID_BARE.search("the id is 985-73-8194 somewhere")
        assert m is not None
        assert m.group("value") == "985-73-8194"

    def test_does_not_match_random_digits(self):
        assert TAX_ID_BARE.search("985738194") is None  # no dashes


# ----- IBAN ---------------------------------------------------------------


class TestIbanAnchored:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("IBAN: GB81LZWO32519172531418", "GB81LZWO32519172531418"),
            ("IBAN:GB81LZWO32519172531418", "GB81LZWO32519172531418"),
            ("iban  GB81LZWO32519172531418", "GB81LZWO32519172531418"),  # lower
            ("IBAN: GB20BAKH22085364527355", "GB20BAKH22085364527355"),
        ],
    )
    def test_matches(self, text, expected):
        m = IBAN_ANCHORED.search(text)
        assert m is not None
        assert m.group("value").upper() == expected

    def test_rejects_too_short(self):
        # 2 letters + 2 digits + only 8 alphanumerics = too short
        assert IBAN_ANCHORED.search("IBAN: GB12ABCDE12345") is None


class TestIbanBare:
    def test_matches_in_freetext(self):
        m = IBAN_BARE.search("please pay to GB81LZWO32519172531418 asap")
        assert m is not None
        assert m.group("value") == "GB81LZWO32519172531418"

    def test_does_not_match_address(self):
        # "RI 12335" is state code + zip — only 5 digits, not 11+ alphanumerics after.
        assert IBAN_BARE.search("Lake Jonathan, RI 12335") is None
