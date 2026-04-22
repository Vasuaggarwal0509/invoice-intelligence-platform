"""
Generic text utilities shared across components.

These helpers carry no knowledge of invoice structure, labels, or GST —
they are pure text operations (fuzzy variant match, space reinsertion).
Component-specific dictionaries (e.g. extraction's ``LABEL_VARIANTS``,
tables' invoice-anchor variants) live in their own modules and call
these helpers with their own variant lists.

Put here — rather than duplicated across components — so a future
service split does not need to duplicate regex / fuzzy-match logic.
A component that depends on :mod:`components._common` stays deployable
on its own because `_common` has no component-level dependencies of
its own (only `rapidfuzz` from PyPI).
"""

import re

from rapidfuzz import fuzz


__all__ = [
    "matches_variant",
    "contains_variant",
    "normalize_multiword_spacing",
]


# ---------------------------------------------------------------------------
# Fuzzy variant matching
# ---------------------------------------------------------------------------


def matches_variant(
    text: str,
    variants: list[str],
    threshold: int = 85,
    max_extra_chars: int = 4,
) -> bool:
    """True if ``text`` is approximately *one of* ``variants`` (no trailing value).

    Used for spotting standalone anchor lines like ``"Seller:"``, ``"ITEMS"``,
    ``"SUMMARY"`` in OCR output — rejects label+value lines like
    ``"Seller: Bradley-Andrade"``.

    Args:
        text: Input string (typically an OCR line).
        variants: Candidate variants to match against.
        threshold: ``rapidfuzz`` ratio threshold (0–100) for a match.
        max_extra_chars: Extra characters beyond the longest variant before
            the line is considered "too long to be just a label".
    """
    cleaned = text.strip()
    cleaned_lower = cleaned.lower()
    for variant in variants:
        v_lower = variant.lower()
        if len(cleaned) > len(variant) + max_extra_chars:
            continue
        score = fuzz.ratio(cleaned_lower, v_lower)
        if score >= threshold:
            return True
    return False


def contains_variant(
    text: str,
    variants: list[str],
    threshold: int = 85,
) -> bool:
    """True if ``text`` contains one of ``variants`` anywhere (partial match).

    Used for lines like ``"Invoice no: 12345"`` where the variant is a prefix
    or substring, not the whole line. Uses ``rapidfuzz.partial_ratio``.
    """
    t_lower = text.strip().lower()
    for variant in variants:
        score = fuzz.partial_ratio(t_lower, variant.lower())
        if score >= threshold:
            return True
    return False


# ---------------------------------------------------------------------------
# Multi-word spacing normaliser
# ---------------------------------------------------------------------------
#
# Designed from the 2026-04-18 evaluation failures where OCR collapsed
# spaces inside multi-word values (addresses, item descriptions). Each
# rule fixes one collapse class without risking false splits on state+zip
# patterns (e.g. "WV79662") that the ground truth sometimes keeps joined.
# Uppercase-run merges like "DPOAP69387" → "DPO AP 69387" are *not* fixable
# heuristically — they would need a dictionary to know where "DPO" ends
# and "AP" begins.

_LOWER_TO_UPPER = re.compile(r"(?<=[a-z])(?=[A-Z])")
_DIGIT_TO_UPPER = re.compile(r"(?<=[0-9])(?=[A-Z])")
_LOWER_TO_DIGIT = re.compile(r"(?<=[a-z])(?=[0-9])")
_PUNCT_TO_NONSPACE = re.compile(r"(?<=[,.;])(?=[^\s])")
_MULTIPLE_SPACES = re.compile(r" {2,}")


def normalize_multiword_spacing(text: str) -> str:
    """Insert conventional spaces that OCR sometimes drops.

    Examples::

        >>> normalize_multiword_spacing("9879ElizabethCommon")
        '9879 Elizabeth Common'
        >>> normalize_multiword_spacing("Lake Jonathan,Rl 12335")
        'Lake Jonathan, Rl 12335'
        >>> normalize_multiword_spacing("Unit9678Box9664")
        'Unit 9678 Box 9664'
        >>> normalize_multiword_spacing("Stacy VilleApt.488")
        'Stacy Ville Apt. 488'

    Known limitation — uppercase run merges are not split::

        >>> normalize_multiword_spacing("DPOAP69387")
        'DPOAP 69387'
    """
    if not text:
        return text
    text = _LOWER_TO_UPPER.sub(" ", text)
    text = _DIGIT_TO_UPPER.sub(" ", text)
    text = _LOWER_TO_DIGIT.sub(" ", text)
    text = _PUNCT_TO_NONSPACE.sub(" ", text)
    text = _MULTIPLE_SPACES.sub(" ", text)
    return text.strip()
