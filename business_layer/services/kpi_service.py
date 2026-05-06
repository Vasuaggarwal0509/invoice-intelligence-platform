"""KPI service — assembles the business dashboard payload.

One public function. Delegates all aggregation to
:mod:`business_layer.repositories.kpi_queries` so the service stays
thin enough for the test suite to exercise through route-level
integration tests rather than duplicating math.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.repositories import kpi_queries


@dataclass(frozen=True)
class DashboardPayload:
    """Service-layer analog of :class:`DashboardPublic` — dataclasses, not Pydantic."""

    period_year: int
    period_month: int
    currency: str
    tiles: kpi_queries.KpiTotals
    top_vendors: list[kpi_queries.VendorTotal]
    needs_review: list[kpi_queries.NeedsReviewItem]


def build_dashboard(
    session: Session,
    *,
    workspace_id: str,
    period: str = "this_month",
) -> DashboardPayload:
    """Return the full dashboard payload for the caller's workspace.

    ``period`` accepts ``'this_month'`` or ``'last_month'``. Anything
    else degrades silently to ``'this_month'`` so a frontend bug
    can't break the dashboard render.
    """
    if period not in ("this_month", "last_month"):
        period = "this_month"

    now = dt.datetime.now(dt.UTC)
    if period == "last_month":
        # First of this month → minus one day → previous month.
        last_in_prev = dt.datetime(now.year, now.month, 1, tzinfo=dt.UTC) - dt.timedelta(days=1)
        period_year, period_month = last_in_prev.year, last_in_prev.month
        month_start, month_end = kpi_queries.month_bounds_ms(period_year, period_month)
    else:
        month_start, month_end = kpi_queries.current_month_bounds_ms()
        period_year, period_month = now.year, now.month

    tiles = kpi_queries.totals_for_month(
        session,
        workspace_id=workspace_id,
        month_start_ms=month_start,
        month_end_ms=month_end,
    )
    top_vendors = kpi_queries.top_vendors_for_month(
        session,
        workspace_id=workspace_id,
        month_start_ms=month_start,
        month_end_ms=month_end,
        limit=5,
    )
    needs_review = kpi_queries.needs_review(
        session,
        workspace_id=workspace_id,
        limit=5,
    )

    return DashboardPayload(
        period_year=period_year,
        period_month=period_month,
        currency="INR",  # v1 single-currency; multi-currency is a Sprint 5+ concern
        tiles=tiles,
        top_vendors=top_vendors,
        needs_review=needs_review,
    )
