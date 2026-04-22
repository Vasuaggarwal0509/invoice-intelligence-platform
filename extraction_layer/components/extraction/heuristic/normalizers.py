"""
Thin re-export shim.

The implementation of ``normalize_address_spacing`` now lives in the
neutral :mod:`components._common.text` module (as
``normalize_multiword_spacing``). This shim preserves the historic name
so existing imports (extraction + tests) keep working and so the
component split in 2026-04-19 stays backwards-compatible.

See ``components/_common/text.py`` for the rationale, rules, and
examples.
"""

from extraction_layer.components._common.text import (
    normalize_multiword_spacing as normalize_address_spacing,
)

__all__ = ["normalize_address_spacing"]
