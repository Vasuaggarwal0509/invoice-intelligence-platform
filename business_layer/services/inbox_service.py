"""Inbox service — list + mark-ignored, workspace-scoped.

Routes call these functions with ``workspace_id`` already resolved
from the session. Services never read cookies or request headers.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from business_layer.db.tables import inbox_messages as t_inbox
from business_layer.db.tables import invoices as t_invoices
from business_layer.db.tables import sources as t_sources
from business_layer.errors import NotFoundError
from business_layer.repositories import inbox_messages as inbox_repo


@dataclass(frozen=True)
class InboxRowDc:
    """Service-layer row — joined across inbox + sources + invoices.

    Kept distinct from :class:`InboxMessageRow` (pure repository
    dataclass) to keep repository queries simple + isolate the join
    knowledge here.
    """

    id: str
    invoice_id: str | None
    source_kind: str
    sender: str | None
    subject: str | None
    received_at: int
    content_type: str
    status: str
    vendor_name: str | None
    total_amount_minor: int | None
    currency: str


def list_inbox(
    session: Session,
    *,
    workspace_id: str,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> list[InboxRowDc]:
    """Return inbox rows newest-first with enough context to render the table."""
    stmt = (
        select(
            t_inbox.c.id,
            t_sources.c.kind.label("source_kind"),
            t_inbox.c.sender,
            t_inbox.c.subject,
            t_inbox.c.received_at,
            t_inbox.c.content_type,
            t_inbox.c.status,
            t_invoices.c.id.label("invoice_id"),
            t_invoices.c.vendor_name,
            t_invoices.c.total_amount_minor,
            t_invoices.c.currency,
        )
        .select_from(
            t_inbox.outerjoin(t_sources, t_inbox.c.source_id == t_sources.c.id)
            .outerjoin(t_invoices, t_invoices.c.inbox_message_id == t_inbox.c.id)
        )
        .where(t_inbox.c.workspace_id == workspace_id)
        .order_by(desc(t_inbox.c.received_at))
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(t_inbox.c.status == status)

    rows = session.execute(stmt).all()
    return [
        InboxRowDc(
            id=r.id,
            invoice_id=r.invoice_id,
            source_kind=r.source_kind or "upload",
            sender=r.sender,
            subject=r.subject,
            received_at=r.received_at,
            content_type=r.content_type,
            status=r.status,
            vendor_name=r.vendor_name,
            total_amount_minor=r.total_amount_minor,
            currency=r.currency or "INR",
        )
        for r in rows
    ]


def count_inbox(session: Session, *, workspace_id: str) -> int:
    """Total inbox count for the workspace — for pagination."""
    from sqlalchemy import func

    row = session.execute(
        select(func.count())
        .select_from(t_inbox)
        .where(t_inbox.c.workspace_id == workspace_id)
    ).first()
    return int(row[0]) if row else 0


def mark_ignored(
    session: Session,
    *,
    workspace_id: str,
    message_id: str,
    reason: str | None,
) -> None:
    """Flag an inbox row as ``ignored`` — e.g. "this was spam, not an invoice".

    Raises :class:`NotFoundError` if the message doesn't exist in this
    workspace. The 404 surface intentionally also hides cross-workspace
    reads (an attacker asking for someone else's row gets the same
    response as for a non-existent id).
    """
    existing = inbox_repo.find_by_id_for_workspace(
        session, message_id=message_id, workspace_id=workspace_id
    )
    if existing is None:
        raise NotFoundError("inbox message not found")
    inbox_repo.update_status(
        session,
        message_id=message_id,
        status="ignored",
        ignored_reason=reason or "user_marked",
    )
