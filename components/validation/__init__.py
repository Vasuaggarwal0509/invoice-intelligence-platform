"""Validation component — pipeline stage 9: ExtractionResult + TableExtractionResult -> ValidationResult.

Public surface:

    from components.validation import ValidationEngine

    engine = ValidationEngine()
    result = engine.validate(extraction, tables)

    if result.all_checks_pass():
        ...   # ready for export
    else:
        for finding in result.failures():
            print(finding.rule_name, finding.target, finding.reason)

See README.md for the full rule list and `research.md` §11 for the rules' design rationale.
"""

from .engine import ValidationEngine
from .parsers import parse_european_decimal, parse_percent
from .rules.iban_checksum import iban_is_valid
from .types import RuleFinding, RuleOutcome, ValidationResult

__all__ = [
    "RuleFinding",
    "RuleOutcome",
    "ValidationEngine",
    "ValidationResult",
    "iban_is_valid",
    "parse_european_decimal",
    "parse_percent",
]
