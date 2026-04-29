"""Aggregation queries for the business dashboard.

All queries are workspace-scoped in their WHERE clauses — IDOR defence
lives in the query, not in the caller. A service-layer mistake (e.g.
forgetting to pass ``workspace_id``) surfaces as an empty result, not
a cross-workspace leak.

Period semantics: "this month" uses ``invoices.created_at`` (always
populated at upload time). We do not use ``invoice_date`` because it
arrives post-extraction and may be missing or unparseable. This means
an invoice uploaded today dated last month still counts this month —
correct from the user's ingestion perspective ("what did I add this
month?"). Sprint 5 adds a toggle for accounting-period mode if CAs
ask.

Money is INTEGER paise throughout. Division / display formatting is
strictly a presentation concern — never persisted.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, desc, distinct, exists, func, select
from sqlalchemy.orm import Session

from business_layer.db.tables import invoices as t_invoices
from business_layer.db.tables import validation_findings as t_vf

# ---------- month bounds ------------------------------------------------


def month_bounds_ms(year: int, month: int) -> tuple[int, int]:
    """Return ``(start_ms, end_ms)`` for the given calendar month.

    ``end_ms`` is the first instant of the NEXT month — half-open
    interval matches how SQL ``>=``/``<`` read naturally.
    """
    import calendar
    import datetime as dt

    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1..12, got {month}")
    start = dt.datetime(year, month, 1, tzinfo=dt.UTC)
    # Last day of month + 1 day = first day of next month.
    _, last_day = calendar.monthrange(year, month)
    last_moment = dt.datetime(year, month, last_day, 23, 59, 59, 999_000, tzinfo=dt.UTC)
    end = last_moment + dt.timedelta(milliseconds=1)
    return (int(start.timestamp() * 1000), int(end.timestamp() * 1000))


def current_month_bounds_ms(now_ms_fn=None) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """``month_bounds_ms`` anchored to the process's current UTC clock.

    ``now_ms_fn`` is an injection seam for tests.
    """
    import datetime as dt

    if now_ms_fn is not None:
        ts_ms = now_ms_fn()
        dt_now = dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.UTC)
    else:
        dt_now = dt.datetime.now(dt.UTC)
    return month_bounds_ms(dt_now.year, dt_now.month)


# ---------- DTOs -------------------------------------------------------


@dataclass(frozen=True)
class KpiTotals:
    """The four main tiles on the dashboard.

    ``itc_estimate_minor`` is an **estimate** — it assumes an
    18%-inclusive GST rate typical for most Indian B2B invoices.
    Real ITC depends on the tax breakup per line + GSTR-2B match,
    both of which arrive in Sprint 5. The UI must label this "est.".
    """

    invoices_this_month: int
    total_spend_minor: int
    itc_estimate_minor: int
    needs_review_count: int


@dataclass(frozen=True)
class VendorTotal:
    vendor_name: str
    invoice_count: int
    total_minor: int


@dataclass(frozen=True)
class NeedsReviewItem:
    invoice_id: str
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: str | None
    total_minor: int | None
    created_at: int
    failing_rules: int


# ---------- queries ----------------------------------------------------


def totals_for_month(
    session: Session,
    *,
    workspace_id: str,
    month_start_ms: int,
    month_end_ms: int,
) -> KpiTotals:
    """Return the four dashboard tile values in one round-trip.

    Uses conditional aggregates (CASE WHEN ...) so the DB does all the
    bucketing server-side rather than fetching rows and counting in
    Python.
    """
    # "needs review" = ≥1 FAIL finding for the invoice.
    has_fail_subq = (
        exists()
        .where(
            t_vf.c.invoice_id == t_invoices.c.id,
            t_vf.c.workspace_id == workspace_id,
            t_vf.c.outcome == "FAIL",
        )
        .correlate(t_invoices)
    )

    # ITC estimate: include totals from invoices WITHOUT any FAIL finding,
    # computed at the 18%/118% stripping rate. GST-inclusive assumption.
    #
    # Formula: itc ≈ gross * 18 / 118. We do integer math with truncation —
    # the estimate is already imprecise by design; rounding noise in the
    # last paise doesn't matter.
    clean_total_expr = func.coalesce(
        func.sum(
            case(
                (has_fail_subq, 0),
                else_=func.coalesce(t_invoices.c.total_amount_minor, 0),
            )
        ),
        0,
    )

    stmt = select(
        func.count().label("invoice_count"),
        func.coalesce(func.sum(t_invoices.c.total_amount_minor), 0).label("total_spend"),
        clean_total_expr.label("clean_total"),
        func.coalesce(
            func.sum(case((has_fail_subq, 1), else_=0)),
            0,
        ).label("needs_review_count"),
    ).where(
        t_invoices.c.workspace_id == workspace_id,
        t_invoices.c.created_at >= month_start_ms,
        t_invoices.c.created_at < month_end_ms,
    )
    row = session.execute(stmt).first()
    if row is None:  # pragma: no cover - aggregate always returns one row
        return KpiTotals(0, 0, 0, 0)

    invoice_count = int(row.invoice_count or 0)
    total_spend = int(row.total_spend or 0)
    clean_total = int(row.clean_total or 0)
    # 18/118 ≈ 0.1525. Integer math avoids float drift.
    itc_estimate = clean_total * 18 // 118
    return KpiTotals(
        invoices_this_month=invoice_count,
        total_spend_minor=total_spend,
        itc_estimate_minor=itc_estimate,
        needs_review_count=int(row.needs_review_count or 0),
    )


def top_vendors_for_month(
    session: Session,
    *,
    workspace_id: str,
    month_start_ms: int,
    month_end_ms: int,
    limit: int = 5,
) -> list[VendorTotal]:
    """Top vendors by total spend this month, non-null vendor only.

    Invoices still waiting on extraction (``vendor_name IS NULL``) are
    excluded — they'd cluster under a useless "Unknown" row.
    """
    stmt = (
        select(
            t_invoices.c.vendor_name,
            func.count().label("n"),
            func.coalesce(func.sum(t_invoices.c.total_amount_minor), 0).label("total_minor"),
        )
        .where(
            t_invoices.c.workspace_id == workspace_id,
            t_invoices.c.created_at >= month_start_ms,
            t_invoices.c.created_at < month_end_ms,
            t_invoices.c.vendor_name.is_not(None),
        )
        .group_by(t_invoices.c.vendor_name)
        .order_by(desc("total_minor"))
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return [
        VendorTotal(
            vendor_name=r.vendor_name,
            invoice_count=int(r.n or 0),
            total_minor=int(r.total_minor or 0),
        )
        for r in rows
    ]


def needs_review(
    session: Session,
    *,
    workspace_id: str,
    limit: int = 5,
) -> list[NeedsReviewItem]:
    """Invoices with ≥1 failing rule — ordered newest-first.

    Not restricted to the current month — reviewing old failing
    invoices is still valuable (they may be the ones the user has been
    ignoring).
    """
    failing_count = (
        select(func.count())
        .select_from(t_vf)
        .where(
            t_vf.c.invoice_id == t_invoices.c.id,
            t_vf.c.workspace_id == workspace_id,
            t_vf.c.outcome == "FAIL",
        )
        .correlate(t_invoices)
        .scalar_subquery()
    )

    stmt = (
        select(
            t_invoices.c.id,
            t_invoices.c.vendor_name,
            t_invoices.c.invoice_no,
            t_invoices.c.invoice_date,
            t_invoices.c.total_amount_minor,
            t_invoices.c.created_at,
            failing_count.label("failing_rules"),
        )
        .where(
            t_invoices.c.workspace_id == workspace_id,
            failing_count > 0,
        )
        .order_by(desc(t_invoices.c.created_at))
        .limit(limit)
    )
    rows = session.execute(stmt).all()
    return [
        NeedsReviewItem(
            invoice_id=r.id,
            vendor_name=r.vendor_name,
            invoice_no=r.invoice_no,
            invoice_date=r.invoice_date,
            total_minor=int(r.total_amount_minor) if r.total_amount_minor is not None else None,
            created_at=int(r.created_at),
            failing_rules=int(r.failing_rules or 0),
        )
        for r in rows
    ]


def unique_vendor_count(session: Session, *, workspace_id: str) -> int:
    """Distinct vendors the workspace has ever had — for flavour text."""
    row = session.execute(
        select(func.count(distinct(t_invoices.c.vendor_name))).where(
            t_invoices.c.workspace_id == workspace_id,
            t_invoices.c.vendor_name.is_not(None),
        )
    ).first()
    return int(row[0]) if row and row[0] else 0
