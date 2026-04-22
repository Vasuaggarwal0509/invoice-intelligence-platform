"""Tests for exact-match duplicate detection within a batch."""

from components.validation.rules.duplicates import detect_duplicates
from components.validation.types import RuleOutcome

from ._fixtures import make_extraction


class TestNoDuplicates:
    def test_all_distinct_pass(self):
        batch = [
            make_extraction(invoice_no="1", seller_tax_id="111-11-1111", invoice_date="01/01/2024"),
            make_extraction(invoice_no="2", seller_tax_id="222-22-2222", invoice_date="02/02/2024"),
            make_extraction(invoice_no="3", seller_tax_id="333-33-3333", invoice_date="03/03/2024"),
        ]
        findings = detect_duplicates(batch)
        assert len(findings) == 3
        for f_list in findings:
            assert len(f_list) == 1
            assert f_list[0].outcome == RuleOutcome.PASS

    def test_empty_batch_returns_empty(self):
        assert detect_duplicates([]) == []


class TestWithDuplicates:
    def test_two_identical_both_flagged(self):
        dup = make_extraction(invoice_no="77", seller_tax_id="999-99-9999", invoice_date="05/05/2024")
        batch = [dup, dup]
        findings = detect_duplicates(batch)
        assert len(findings) == 2
        for f_list in findings:
            assert f_list[0].outcome == RuleOutcome.FAIL
            assert "duplicate" in f_list[0].reason.lower()

    def test_triplet_all_three_flagged(self):
        dup = make_extraction(invoice_no="77", seller_tax_id="999-99-9999", invoice_date="05/05/2024")
        batch = [dup, dup, dup]
        findings = detect_duplicates(batch)
        assert len(findings) == 3
        assert all(f_list[0].outcome == RuleOutcome.FAIL for f_list in findings)

    def test_mixed_batch(self):
        dup = make_extraction(invoice_no="77", seller_tax_id="999-99-9999", invoice_date="05/05/2024")
        distinct = make_extraction(
            invoice_no="78", seller_tax_id="888-88-8888", invoice_date="06/06/2024"
        )
        batch = [dup, distinct, dup]
        findings = detect_duplicates(batch)
        assert findings[0][0].outcome == RuleOutcome.FAIL
        assert findings[1][0].outcome == RuleOutcome.PASS
        assert findings[2][0].outcome == RuleOutcome.FAIL

    def test_reason_mentions_other_indexes(self):
        dup = make_extraction(invoice_no="77", seller_tax_id="999-99-9999", invoice_date="05/05/2024")
        batch = [dup, dup]
        findings = detect_duplicates(batch)
        assert "1" in findings[0][0].reason
        assert "0" in findings[1][0].reason


class TestNotApplicable:
    def test_missing_invoice_no_not_applicable(self):
        batch = [make_extraction(invoice_no=None)]
        findings = detect_duplicates(batch)
        assert findings[0][0].outcome == RuleOutcome.NOT_APPLICABLE

    def test_missing_seller_tax_id_not_applicable(self):
        batch = [make_extraction(seller_tax_id=None)]
        findings = detect_duplicates(batch)
        assert findings[0][0].outcome == RuleOutcome.NOT_APPLICABLE

    def test_missing_date_not_applicable(self):
        batch = [make_extraction(invoice_date=None)]
        findings = detect_duplicates(batch)
        assert findings[0][0].outcome == RuleOutcome.NOT_APPLICABLE
