"""
Label variant dictionary + extraction-domain wrappers.

Reason this lives separately from the regex patterns (``regex_patterns.py``):
regex captures **label + value in one line** (e.g. ``Invoice no: 12345``,
``Taxld:985-73-8194``). The dictionary here is used to **anchor positions**
in the document — locating where "Seller:" or "ITEMS" starts so the
column-based rules in ``columns.py`` know where to begin and where to stop.

The 2026-04-18 spot-check showed consistent, predictable label variants
across katanaml. ``rapidfuzz`` partial / ratio match over a variant list
gives robust tolerance for OCR digit-letter mistakes (e.g. "Taxld" for
"Tax Id").

Implementation split:
  * The generic matching primitives live in :mod:`components._common.text`.
  * The invoice-structure anchors (``items_start``, ``summary_start``) live
    in :mod:`components._common.invoice_anchors` — shared with the tables
    component.
  * Everything *extraction-specific* (all the other LABEL_VARIANTS keys
    plus the ``line_is_label`` / ``line_contains_label`` wrappers that
    take a key rather than a variant list) stays here.
"""

from extraction_layer.components._common.invoice_anchors import (
    ITEMS_START_VARIANTS,
    SUMMARY_START_VARIANTS,
)
from extraction_layer.components._common.text import contains_variant, matches_variant

# Keyed by canonical label name. Variants include OCR-quirk forms observed
# in the 2026-04-18 spot-check ("Invoiceno", "Invoicen0", "Taxld", etc.).
# Structural anchors (``items_start`` / ``summary_start``) reference the
# shared lists from ``_common`` so tables and extraction stay in sync.
LABEL_VARIANTS: dict[str, list[str]] = {
    "seller": ["Seller", "Seller:", "From", "From:"],
    "client": ["Client", "Client:", "Bill to", "Bill to:", "Billed to:"],
    "invoice_no": [
        "Invoice no",
        "Invoiceno",
        "Invoicen0",
        "Invoice no.",
        "Invoice no:",
        "Invoice no :",
        "Invoice #",
        "Invoice Number",
    ],
    "date": [
        "Date of issue",
        "Date of issue:",
        "Invoice date",
        "Issue date",
        "Date:",
        "Date",
    ],
    "tax_id": [
        "Tax Id",
        "Tax Id:",
        "Taxld",
        "Taxld:",
        "Tax ld",
        "Tax ld:",
        "Tax ID",
        "TaxId",
        "Tax No",
    ],
    "iban": ["IBAN", "IBAN:"],
    "items_start": ITEMS_START_VARIANTS,
    "summary_start": SUMMARY_START_VARIANTS,
}


def line_is_label(
    text: str,
    label_key: str,
    threshold: int = 85,
    max_extra_chars: int = 4,
) -> bool:
    """True if ``text`` is approximately just the label for ``label_key``.

    Domain wrapper around :func:`components._common.text.matches_variant`
    that looks the variant list up in :data:`LABEL_VARIANTS`.
    """
    if label_key not in LABEL_VARIANTS:
        return False
    return matches_variant(
        text,
        LABEL_VARIANTS[label_key],
        threshold=threshold,
        max_extra_chars=max_extra_chars,
    )


def line_contains_label(
    text: str,
    label_key: str,
    threshold: int = 85,
) -> bool:
    """True if ``text`` contains one of the ``label_key`` variants.

    Domain wrapper around :func:`components._common.text.contains_variant`.
    """
    if label_key not in LABEL_VARIANTS:
        return False
    return contains_variant(
        text,
        LABEL_VARIANTS[label_key],
        threshold=threshold,
    )
