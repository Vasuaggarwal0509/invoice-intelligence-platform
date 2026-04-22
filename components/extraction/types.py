"""
Output types for the extraction component.

`ExtractionResult` is the contract between the extraction stage (pipeline
step 6 in `project.md` §3.1) and every downstream stage — validation,
export, UI. Changing any field here is a pipeline-wide change.

The schema is deliberately flat: one dict of named fields. Each field
carries the extracted value, a confidence score, and a provenance tag
saying which rule produced it. Consumers never branch on extractor
identity — only on value / confidence / source.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractedField(BaseModel):
    """One extracted field from an invoice."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1, description="Field key, e.g. 'invoice_no'.")
    value: str | None = Field(
        default=None,
        description="Extracted string; None if the extractor did not find the field.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="0.0 means 'not found'. Higher means the extractor is more sure.",
    )
    source: str = Field(
        default="none",
        description=(
            "Which rule produced this field: 'regex', 'label_anchor', "
            "'column_heuristic', or 'none'."
        ),
    )
    source_detail: str | None = Field(
        default=None,
        description="Human-readable note about the exact rule, e.g. 'Invoice no anchor'.",
    )


class ExtractionResult(BaseModel):
    """Everything the extraction stage produces for one invoice."""

    model_config = ConfigDict(frozen=True)

    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    extractor: str = Field(
        ...,
        min_length=1,
        description="Extractor identifier, e.g. 'heuristic'.",
    )
    duration_ms: float = Field(..., ge=0.0)
    diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional per-run diagnostics (e.g. detected column boundary).",
    )

    def get_value(self, name: str) -> str | None:
        """Convenience: return the field value or None if absent / empty."""
        field = self.fields.get(name)
        if field is None:
            return None
        return field.value
