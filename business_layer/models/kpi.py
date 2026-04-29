"""KPI response DTOs for the business dashboard.

Money fields are INTEGER minor units (paise for INR) on the wire —
the frontend formats. Keeps the contract free of floating-point drift
across JSON round-trips.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class KpiTilesPublic(BaseModel):
    """The four headline tiles."""

    model_config = ConfigDict(frozen=True)

    invoices_this_month: int
    total_spend_minor: int
    itc_estimate_minor: int
    needs_review_count: int


class VendorTotalPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    vendor_name: str
    invoice_count: int
    total_minor: int


class NeedsReviewItemPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    invoice_id: str
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: str | None
    total_minor: int | None
    created_at: int
    failing_rules: int


class DashboardPublic(BaseModel):
    """One-shot response for ``GET /api/business/dashboard``.

    Packages every piece the dashboard needs into one round-trip so the
    UI renders in a single paint — no flash of partial data.
    """

    model_config = ConfigDict(frozen=True)

    period_year: int
    period_month: int
    currency: str
    tiles: KpiTilesPublic
    top_vendors: list[VendorTotalPublic]
    needs_review: list[NeedsReviewItemPublic]
