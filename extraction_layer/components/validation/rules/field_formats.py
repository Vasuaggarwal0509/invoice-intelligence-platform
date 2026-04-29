"""
Format validators for the katanaml header schema.

All rules follow the same shape: take an `ExtractionResult`, return a
single `RuleFinding`. If the field was not extracted (value is None),
the rule returns NOT_APPLICABLE (a missing field is an extraction
problem, not a validation problem).
"""

import re
from datetime import datetime

from extraction_layer.components.extraction.types import ExtractionResult

from ..types import RuleFinding, RuleOutcome

_INVOICE_NO = re.compile(r"^\d{6,10}$")
_TAX_ID = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_IBAN_SHAPE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_DATE_FORMAT = "%m/%d/%Y"


def _not_applicable(rule: str, target: str, reason: str) -> RuleFinding:
    return RuleFinding(
        rule_name=rule,
        target=target,
        outcome=RuleOutcome.NOT_APPLICABLE,
        reason=reason,
    )


def _pass(rule: str, target: str) -> RuleFinding:
    return RuleFinding(rule_name=rule, target=target, outcome=RuleOutcome.PASS)


def _fail(rule: str, target: str, reason: str, observed: str | None = None) -> RuleFinding:
    return RuleFinding(
        rule_name=rule,
        target=target,
        outcome=RuleOutcome.FAIL,
        reason=reason,
        observed=observed,
    )


def validate_invoice_no(extraction: ExtractionResult) -> RuleFinding:
    """Invoice number must be 6-10 digits (katanaml uses 8)."""
    value = extraction.get_value("invoice_no")
    if value is None:
        return _not_applicable("invoice_no_format", "invoice_no", "field not extracted")
    if _INVOICE_NO.match(value):
        return _pass("invoice_no_format", "invoice_no")
    return _fail(
        "invoice_no_format",
        "invoice_no",
        "must be 6-10 digits",
        observed=value,
    )


def validate_invoice_date(extraction: ExtractionResult) -> RuleFinding:
    """Invoice date must parse as MM/DD/YYYY (katanaml convention)."""
    value = extraction.get_value("invoice_date")
    if value is None:
        return _not_applicable("invoice_date_format", "invoice_date", "field not extracted")
    try:
        datetime.strptime(value, _DATE_FORMAT)
        return _pass("invoice_date_format", "invoice_date")
    except ValueError:
        return _fail(
            "invoice_date_format",
            "invoice_date",
            f"does not parse as {_DATE_FORMAT}",
            observed=value,
        )


def validate_seller_tax_id(extraction: ExtractionResult) -> RuleFinding:
    return _validate_tax_id(extraction, "seller_tax_id")


def validate_client_tax_id(extraction: ExtractionResult) -> RuleFinding:
    return _validate_tax_id(extraction, "client_tax_id")


def _validate_tax_id(extraction: ExtractionResult, field: str) -> RuleFinding:
    value = extraction.get_value(field)
    if value is None:
        return _not_applicable("tax_id_format", field, "field not extracted")
    if _TAX_ID.match(value):
        return _pass("tax_id_format", field)
    return _fail(
        "tax_id_format",
        field,
        "must match XXX-XX-XXXX",
        observed=value,
    )


def validate_iban_shape(extraction: ExtractionResult) -> RuleFinding:
    """IBAN must match the structural pattern before its checksum is worth computing."""
    value = extraction.get_value("iban")
    if value is None:
        return _not_applicable("iban_shape", "iban", "field not extracted")
    normalised = value.replace(" ", "").upper()
    if _IBAN_SHAPE.match(normalised):
        return _pass("iban_shape", "iban")
    return _fail(
        "iban_shape",
        "iban",
        "must match country-prefix + 2 check digits + 11-30 alphanumerics",
        observed=value,
    )
