"""CA-dashboard aggregation queries.

The CA persona is read-only across their client workspaces — so all
queries here are SELECTs that JOIN across ``workspaces`` +
``invoices`` + ``validation_findings``, filtered on the CA's own GSTIN.

Workspace isolation invariant: a row is visible to the CA iff the
business's ``workspaces.ca_gstin`` equals the CA's own
``workspaces.gstin``. That filter lives inline in every query here —
same pattern as the per-workspace IDOR defence in
:mod:`business_layer.repositories.kpi_queries`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from business_layer.db.tables import (
    invoices as t_invoices,
)
from business_layer.db.tables import (
    validation_findings as t_vf,
)
from business_layer.db.tables import (
    workspaces as t_ws,
)


@dataclass(frozen=True)
class CaClientRow:
    """One entry in the CA's client list — a business workspace + its rollup."""

    workspace_id: str
    name: str
    gstin: str | None
    invoice_count: int
    total_spend_minor: int
    open_flags: int  # SUM of FAIL findings across their invoices


def list_clients(session: Session, *, ca_gstin: str) -> list[CaClientRow]:
    """Return the CA's clients, each with aggregate rollups.

    Computed in one round-trip via two correlated sub-aggregates on
    ``invoices`` and ``validation_findings``. No per-client Python
    loop.
    """
    invoice_agg = (
        select(
            t_invoices.c.workspace_id.label("workspace_id"),
            func.count().label("invoice_count"),
            func.coalesce(func.sum(t_invoices.c.total_amount_minor), 0).label("total_spend"),
        )
        .group_by(t_invoices.c.workspace_id)
        .subquery()
    )

    flag_agg = (
        select(
            t_vf.c.workspace_id.label("workspace_id"),
            func.count().label("open_flags"),
        )
        .where(t_vf.c.outcome == "FAIL")
        .group_by(t_vf.c.workspace_id)
        .subquery()
    )

    stmt = (
        select(
            t_ws.c.id.label("workspace_id"),
            t_ws.c.name,
            t_ws.c.gstin,
            func.coalesce(invoice_agg.c.invoice_count, 0).label("invoice_count"),
            func.coalesce(invoice_agg.c.total_spend, 0).label("total_spend"),
            func.coalesce(flag_agg.c.open_flags, 0).label("open_flags"),
        )
        .select_from(
            t_ws.outerjoin(invoice_agg, invoice_agg.c.workspace_id == t_ws.c.id).outerjoin(
                flag_agg, flag_agg.c.workspace_id == t_ws.c.id
            )
        )
        .where(t_ws.c.ca_gstin == ca_gstin)
        .order_by(t_ws.c.name)
    )

    rows = session.execute(stmt).all()
    return [
        CaClientRow(
            workspace_id=r.workspace_id,
            name=r.name,
            gstin=r.gstin,
            invoice_count=int(r.invoice_count),
            total_spend_minor=int(r.total_spend),
            open_flags=int(r.open_flags),
        )
        for r in rows
    ]


def is_ca_authorised_for_workspace(
    session: Session,
    *,
    ca_gstin: str,
    workspace_id: str,
) -> bool:
    """Gate check used by every CA → client-specific route.

    Returns True iff ``workspace_id`` belongs to a business that has
    this CA's GSTIN as their ``ca_gstin``. The service layer calls
    this BEFORE any invoice / inbox read for the client.

    Cross-persona defence: if a business tries to hit
    ``/api/ca/clients/{id}/...`` the session has role='business' and
    never reaches this function; the route dependency would 403 first.
    """
    row = session.execute(
        select(t_ws.c.id).where(t_ws.c.id == workspace_id, t_ws.c.ca_gstin == ca_gstin).limit(1)
    ).first()
    return row is not None


@dataclass(frozen=True)
class CaClientInvoiceRow:
    """Summary row for the CA → client → invoices view."""

    invoice_id: str
    vendor_name: str | None
    invoice_no: str | None
    invoice_date: str | None
    total_amount_minor: int | None
    currency: str
    status: str
    failing_rules: int
    created_at: int


def list_client_invoices(
    session: Session,
    *,
    ca_gstin: str,
    workspace_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[CaClientInvoiceRow]:
    """Return invoices for one client, newest first.

    Double-gated: ``workspaces.ca_gstin = ca_gstin`` in the JOIN
    ensures a CA only sees invoices from workspaces they're linked
    to, even if a caller tampers with ``workspace_id``.
    """
    failing_count = (
        select(func.count())
        .select_from(t_vf)
        .where(
            t_vf.c.invoice_id == t_invoices.c.id,
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
            t_invoices.c.currency,
            t_invoices.c.status,
            t_invoices.c.created_at,
            failing_count.label("failing_rules"),
        )
        .select_from(t_invoices.join(t_ws, t_ws.c.id == t_invoices.c.workspace_id))
        .where(
            t_ws.c.id == workspace_id,
            t_ws.c.ca_gstin == ca_gstin,
        )
        .order_by(desc(t_invoices.c.created_at))
        .limit(limit)
        .offset(offset)
    )

    rows = session.execute(stmt).all()
    return [
        CaClientInvoiceRow(
            invoice_id=r.id,
            vendor_name=r.vendor_name,
            invoice_no=r.invoice_no,
            invoice_date=r.invoice_date,
            total_amount_minor=int(r.total_amount_minor)
            if r.total_amount_minor is not None
            else None,
            currency=r.currency,
            status=r.status,
            failing_rules=int(r.failing_rules or 0),
            created_at=int(r.created_at),
        )
        for r in rows
    ]
