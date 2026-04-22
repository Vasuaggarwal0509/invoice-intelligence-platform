"""Neutral utilities shared across components.

Only things live here that are:
  * genuinely generic (pure text / regex / math), OR
  * shared structural anchors (see :mod:`invoice_anchors`) that would
    otherwise need to be duplicated across multiple components.

Components depend on ``_common``; ``_common`` depends only on PyPI
packages (``rapidfuzz``). No component imports from another component.
"""

from .invoice_anchors import ITEMS_START_VARIANTS, SUMMARY_START_VARIANTS
from .text import contains_variant, matches_variant, normalize_multiword_spacing

__all__ = [
    "ITEMS_START_VARIANTS",
    "SUMMARY_START_VARIANTS",
    "contains_variant",
    "matches_variant",
    "normalize_multiword_spacing",
]
