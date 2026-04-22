"""
Compiled regex patterns for G1 field extraction.

Every pattern is crafted from the 2026-04-18 spot-check observations:

- ``Invoice no`` is often concatenated with its value (`Invoiceno:97159829`)
  and sometimes OCR-corrupted to `Invoicen0`. The regex tolerates optional
  whitespace around the label, accepts both `no` and `n0`, and optional
  colon / period.
- ``Date of issue`` appears on its own line above the actual date; but the
  date regex is permissive enough to fire without an anchor (MM/DD/YYYY
  is a distinctive pattern).
- ``Tax Id`` is systematically OCR'd as ``Taxld`` (I → l) or ``Tax ld``.
  The regex matches ``I`` / ``l`` / ``1`` in the second character.
- ``IBAN`` is typically ``GB + 2 digits + 4 letters + digits`` for UK
  accounts; we use a broader ISO 13616 pattern so non-GB IBANs also match.

Each pattern is case-insensitive and captures the value in group 1.
"""

import re


# Invoice number: e.g. "Invoice no: 12345", "Invoiceno:12345", "Invoicen0:12345"
# The label + optional punctuation + 4+ digits.
INVOICE_NO = re.compile(
    r"""
    invoice          # the word 'invoice'
    \s*              # optional whitespace
    n[o0]            # 'no' or 'n0' (OCR: letter o -> digit 0)
    \s*
    [.:]*            # optional punctuation
    \s*
    (?P<value>\d{4,})
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Bare invoice-number fallback: used when the label was not captured.
# Looks for a standalone 6-10 digit integer on its own line.
INVOICE_NO_BARE = re.compile(r"^\s*(?P<value>\d{6,10})\s*$")


# Invoice date: accepts MM/DD/YYYY, M/D/YY, DD-MM-YYYY, DD/MM/YYYY etc.
# Captured group is the date string as-is; the extractor normalises downstream.
# Preferred with an anchor; fallback pattern for bare dates in the header.
DATE_ANCHORED = re.compile(
    r"""
    (?: date\s*of\s*issue | invoice\s*date | issue\s*date | date )
    \s*[:.]?\s*
    (?P<value>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})
    """,
    re.IGNORECASE | re.VERBOSE,
)

DATE_BARE = re.compile(r"^\s*(?P<value>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*$")


# Tax ID in SSN-like format: XXX-XX-XXXX
# Label variants: 'Tax Id', 'Taxld', 'Tax ld', 'TaxId', 'Tax ID', 'Tax No'
# Second-character class accepts I, l, 1 (OCR confusions).
TAX_ID_ANCHORED = re.compile(
    r"""
    tax
    \s*
    [IlL1]d           # 'Id', 'ld', '1d', 'Ld'
    \s*[:.]?\s*
    (?P<value>\d{3}-\d{2}-\d{4})
    """,
    re.IGNORECASE | re.VERBOSE,
)

TAX_ID_BARE = re.compile(r"(?P<value>\d{3}-\d{2}-\d{4})")


# IBAN: ISO 13616 — 2 letters (country) + 2 digits (checksum) + 11 to 30
# alphanumerics. We broaden slightly to catch UK (22 chars) through longer
# Eastern-European IBANs (up to 34 chars total).
IBAN_ANCHORED = re.compile(
    r"""
    iban
    \s*[:.]?\s*
    (?P<value>[A-Z]{2}\d{2}[A-Z0-9]{11,30})
    """,
    re.IGNORECASE | re.VERBOSE,
)

IBAN_BARE = re.compile(r"(?P<value>[A-Z]{2}\d{2}[A-Z0-9]{11,30})")


__all__ = [
    "INVOICE_NO",
    "INVOICE_NO_BARE",
    "DATE_ANCHORED",
    "DATE_BARE",
    "TAX_ID_ANCHORED",
    "TAX_ID_BARE",
    "IBAN_ANCHORED",
    "IBAN_BARE",
]
