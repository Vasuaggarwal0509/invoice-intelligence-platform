"""
Shared invoice-structure anchor variants.

Both the extraction component (for column detection) and the tables
component (for items-region bounding) need to recognise the same anchor
lines in OCR output. Keeping the variant lists here — in neutral
``_common`` — means a future service split does not end up with two
copies drifting apart.

Only **structural** anchors live here. Extraction-specific label variants
(``invoice_no``, ``tax_id``, ``iban`` …) stay in
``components/extraction/heuristic/labels.py`` because they are part of
extraction's domain, not a shared structural signal.
"""

__all__ = [
    "ITEMS_START_VARIANTS",
    "SUMMARY_START_VARIANTS",
]


# Top of the line-items table.
ITEMS_START_VARIANTS: list[str] = ["ITEMS", "Items", "LINE ITEMS", "Line items"]

# Top of the totals / summary block — bounds the bottom of the items table.
SUMMARY_START_VARIANTS: list[str] = ["SUMMARY", "Summary", "Totals", "Total"]
