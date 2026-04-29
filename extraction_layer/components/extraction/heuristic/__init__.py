"""Heuristic extractor — G1 regex + G2 label-anchor dictionary + column detection."""

from .columns import ColumnLayout, detect_columns
from .extractor import HeuristicExtractor
from .labels import LABEL_VARIANTS, line_contains_label, line_is_label

__all__ = [
    "LABEL_VARIANTS",
    "ColumnLayout",
    "HeuristicExtractor",
    "detect_columns",
    "line_contains_label",
    "line_is_label",
]
