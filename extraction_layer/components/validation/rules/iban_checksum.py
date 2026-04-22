"""
IBAN checksum validation (ISO 13616 mod-97).

Algorithm (per ISO 13616-1:2020 / ECBS):

  1. Move the first four characters (country + 2 check digits) to the end.
  2. Convert each letter to a two-digit number: A=10, B=11, ..., Z=35.
  3. Interpret the resulting string as a decimal integer.
  4. Valid iff that integer mod 97 == 1.

This catches the class of OCR corruption seen on the katanaml test
split's `iban` field — character dropout inside the BBAN and `S ↔ 5`
or `O ↔ 0` confusion — where the confidence scores were 0.99+ but
the value was wrong.
"""

import re
import string

from extraction_layer.components.extraction.types import ExtractionResult

from ..types import RuleFinding, RuleOutcome


_IBAN_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]+$")


def iban_is_valid(iban: str) -> bool:
    """Pure function: run the mod-97 check. True iff the IBAN is valid."""
    if not iban:
        return False
    normalised = iban.strip().replace(" ", "").upper()
    if not _IBAN_PATTERN.match(normalised):
        return False
    rearranged = normalised[4:] + normalised[:4]
    # Letter -> 2-digit number (A=10, ..., Z=35); digits pass through.
    digits = []
    for ch in rearranged:
        if ch.isdigit():
            digits.append(ch)
        elif ch in string.ascii_uppercase:
            digits.append(str(ord(ch) - ord("A") + 10))
        else:  # pragma: no cover — _IBAN_PATTERN already rejected these
            return False
    try:
        return int("".join(digits)) % 97 == 1
    except ValueError:  # pragma: no cover - numeric conversion can't fail here
        return False


def validate_iban_checksum(extraction: ExtractionResult) -> RuleFinding:
    """Run the mod-97 check on the extracted `iban` value."""
    value = extraction.get_value("iban")
    if value is None:
        return RuleFinding(
            rule_name="iban_checksum",
            target="iban",
            outcome=RuleOutcome.NOT_APPLICABLE,
            reason="field not extracted",
        )
    if iban_is_valid(value):
        return RuleFinding(
            rule_name="iban_checksum",
            target="iban",
            outcome=RuleOutcome.PASS,
        )
    return RuleFinding(
        rule_name="iban_checksum",
        target="iban",
        outcome=RuleOutcome.FAIL,
        reason="mod-97 check failed (OCR corruption or invalid IBAN)",
        observed=value,
    )
