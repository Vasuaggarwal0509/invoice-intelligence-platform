"""End-to-end tests for HeuristicExtractor on synthetic OCR fixtures."""

import pytest

from extraction_layer.components.extraction import make_extractor
from extraction_layer.components.extraction.types import ExtractionResult

from ._fixtures import sample00_like_ocr, sample04_like_ocr


@pytest.fixture
def extractor():
    return make_extractor("heuristic")


class TestSample00Like:
    @pytest.fixture
    def result(self, extractor) -> ExtractionResult:
        return extractor.extract(sample00_like_ocr())

    def test_returns_extractionresult(self, result):
        assert isinstance(result, ExtractionResult)
        assert result.extractor == "heuristic"
        assert result.duration_ms >= 0

    def test_invoice_no_extracted(self, result):
        assert result.get_value("invoice_no") == "97159829"
        assert result.fields["invoice_no"].confidence > 0.5
        assert result.fields["invoice_no"].source == "regex"

    def test_invoice_date_extracted(self, result):
        # Anchor "Date of issue:" is on its own line, date on the next.
        # Fallback "bare after anchor" should catch this.
        assert result.get_value("invoice_date") == "09/18/2015"

    def test_seller_tax_id_extracted(self, result):
        # OCR quirk: "Taxld:985-73-8194"
        assert result.get_value("seller_tax_id") == "985-73-8194"
        assert result.fields["seller_tax_id"].confidence > 0.5

    def test_client_tax_id_extracted(self, result):
        assert result.get_value("client_tax_id") == "994-72-1270"

    def test_iban_extracted_upper(self, result):
        # OCR quirk: "IBAN:GB81..." concatenated with no space.
        assert result.get_value("iban") == "GB81LZWO32519172531418"

    def test_seller_multiline_aggregated(self, result):
        seller = result.get_value("seller")
        assert seller is not None
        assert "Bradley-Andrade" in seller
        assert "9879 Elizabeth Common" in seller
        assert "Lake Jonathan, RI 12335" in seller
        # Should NOT contain the tax-id or iban lines.
        assert "985-73-8194" not in seller
        assert "GB81" not in seller

    def test_client_multiline_aggregated(self, result):
        client = result.get_value("client")
        assert client is not None
        assert "Castro PLC" in client
        assert "Unit 9678 Box 9664" in client
        assert "DPO AP 69387" in client
        assert "994-72-1270" not in client

    def test_diagnostics_has_column_split(self, result):
        assert "column_split_x" in result.diagnostics
        assert result.diagnostics["column_split_x"] == 325.0


class TestSample04Like:
    """Second synthetic sample covering a different content but same layout."""

    @pytest.fixture
    def result(self, extractor) -> ExtractionResult:
        return extractor.extract(sample04_like_ocr())

    def test_invoice_no(self, result):
        assert result.get_value("invoice_no") == "16662010"

    def test_invoice_date(self, result):
        assert result.get_value("invoice_date") == "08/28/2016"

    def test_seller_tax_id(self, result):
        assert result.get_value("seller_tax_id") == "959-84-2124"

    def test_client_tax_id(self, result):
        assert result.get_value("client_tax_id") == "938-85-4960"

    def test_iban(self, result):
        assert result.get_value("iban") == "GB20BAKH22085364527355"

    def test_seller_name_in_seller(self, result):
        assert "Smith-Cook" in result.get_value("seller")

    def test_client_name_in_client(self, result):
        assert "Snyder-Johnson" in result.get_value("client")


class TestNoneFields:
    def test_missing_invoice_no_returns_none_field(self, extractor):
        from ._fixtures import make_line
        from extraction_layer.components.ocr.types import OCRResult, PageSize

        # OCR with no invoice-no pattern anywhere.
        ocr = OCRResult(
            tokens=[],
            lines=[make_line("Seller:", 100, 100, 200, 130)],
            page=PageSize(width=800, height=1000),
            backend="synthetic",
            duration_ms=0.0,
        )
        r = extractor.extract(ocr)
        assert r.fields["invoice_no"].value is None
        assert r.fields["invoice_no"].confidence == 0.0
        assert r.fields["invoice_no"].source == "none"
