"""
Output types for the table-extraction component.

`TableExtractionResult` is the contract between the table-extraction stage
(pipeline step 7 in `project.md` §3.1) and every downstream stage —
validation (totals-sum check), export (line-item CSV), UI. Changing any
field here is a pipeline-wide change.

The `InvoiceItem` schema mirrors the katanaml Donut ground-truth fields
exactly (`item_desc`, `item_qty`, `item_net_price`, `item_net_worth`,
`item_vat`, `item_gross_worth`) so evaluation can compare apples-to-apples
against the reference `items` array.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvoiceItem(BaseModel):
    """One line item from an invoice. All fields optional — unmatched values are None."""

    model_config = ConfigDict(frozen=True)

    item_desc: str | None = None
    item_qty: str | None = None
    item_net_price: str | None = None
    item_net_worth: str | None = None
    item_vat: str | None = None
    item_gross_worth: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Dict view matching the Donut ground-truth schema keys."""
        return {
            "item_desc": self.item_desc,
            "item_qty": self.item_qty,
            "item_net_price": self.item_net_price,
            "item_net_worth": self.item_net_worth,
            "item_vat": self.item_vat,
            "item_gross_worth": self.item_gross_worth,
        }


class TableExtractionResult(BaseModel):
    """Everything the table-extraction stage produces for one invoice."""

    model_config = ConfigDict(frozen=True)

    items: list[InvoiceItem] = Field(default_factory=list)
    extractor: str = Field(
        ...,
        min_length=1,
        description="Extractor identifier, e.g. 'spatial'.",
    )
    duration_ms: float = Field(..., ge=0.0)
    diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-run diagnostics (anchor y-coords, detected item count, etc.).",
    )
