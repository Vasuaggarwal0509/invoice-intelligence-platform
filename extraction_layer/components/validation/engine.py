"""
ValidationEngine — orchestrates the individual rules into a
single-record or batch `ValidationResult`.

Usage:

    engine = ValidationEngine()
    result = engine.validate(extraction, tables)

Or in batch, with duplicate detection:

    results = engine.validate_batch(list_of_extractions, list_of_table_results)
"""

from extraction_layer.components.extraction.types import ExtractionResult
from extraction_layer.components.tables.types import TableExtractionResult

from .rules import duplicates, field_formats, iban_checksum, item_arithmetic
from .types import RuleFinding, ValidationResult


class ValidationEngine:
    """Runs all validation rules against one invoice or a batch of them."""

    def validate(
        self,
        extraction: ExtractionResult,
        tables: TableExtractionResult | None = None,
    ) -> ValidationResult:
        """Run single-invoice rules (no cross-record checks)."""
        findings: list[RuleFinding] = [
            field_formats.validate_invoice_no(extraction),
            field_formats.validate_invoice_date(extraction),
            field_formats.validate_seller_tax_id(extraction),
            field_formats.validate_client_tax_id(extraction),
            field_formats.validate_iban_shape(extraction),
            iban_checksum.validate_iban_checksum(extraction),
        ]
        if tables is not None:
            findings.extend(item_arithmetic.validate_all_items(tables))
        return ValidationResult(findings=findings)

    def validate_batch(
        self,
        extractions: list[ExtractionResult],
        tables_list: list[TableExtractionResult | None] | None = None,
    ) -> list[ValidationResult]:
        """Run single-invoice rules plus cross-invoice duplicate detection."""
        if tables_list is None:
            tables_list = [None] * len(extractions)
        if len(tables_list) != len(extractions):
            raise ValueError(
                "tables_list must have the same length as extractions "
                f"({len(extractions)} extractions, {len(tables_list)} tables)"
            )

        per_record: list[list[RuleFinding]] = []
        for extraction, tables in zip(extractions, tables_list, strict=False):
            single = self.validate(extraction, tables)
            per_record.append(list(single.findings))

        duplicate_findings = duplicates.detect_duplicates(extractions)
        results: list[ValidationResult] = []
        for base_findings, dup_findings in zip(per_record, duplicate_findings, strict=False):
            results.append(ValidationResult(findings=base_findings + dup_findings))
        return results
