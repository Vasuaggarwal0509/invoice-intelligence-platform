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
    failure_message: str | None


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
            t_inbox.c.ignored_reason,
            t_invoices.c.id.label("invoice_id"),
            t_invoices.c.vendor_name,
            t_invoices.c.total_amount_minor,
            t_invoices.c.currency,
        )
        .select_from(
            t_inbox.outerjoin(t_sources, t_inbox.c.source_id == t_sources.c.id).outerjoin(
                t_invoices, t_invoices.c.inbox_message_id == t_inbox.c.id
            )
        )
        .where(t_inbox.c.workspace_id == workspace_id)
        .order_by(desc(t_inbox.c.received_at))
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(t_inbox.c.status == status)

    from business_layer.services import findings_messages

    rows = session.execute(stmt).all()
    out: list[InboxRowDc] = []
    for r in rows:
        msg: str | None = None
        if r.status in ("failed", "ignored"):
            msg = findings_messages.inbox_failure_message(r.ignored_reason)
            if msg is None and r.status == "failed":
                # Generic plain-language fallback so the UI never has to
                # show "Failed" with no further context.
                msg = (
                    "We couldn't read this file. Try uploading a clearer "
                    "scan, or forward the email to your CA for manual entry."
                )
        out.append(
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
                failure_message=msg,
            )
        )
    return out


def count_inbox(session: Session, *, workspace_id: str) -> int:
    """Total inbox count for the workspace — for pagination."""
    from sqlalchemy import func

    row = session.execute(
        select(func.count()).select_from(t_inbox).where(t_inbox.c.workspace_id == workspace_id)
    ).first()
    return int(row[0]) if row else 0


def trigger_extract(
    session: Session,
    *,
    workspace_id: str,
    message_ids: list[str] | None,
    all_pending: bool,
) -> dict[str, int]:
    """Enqueue extraction jobs for selected inbox rows.

    Caller picks ONE of two modes:

    * ``message_ids=[...]`` — extract just these rows. Each id is
      verified to belong to the caller's workspace; unknown ids are
      silently dropped (defence against a tampered request).
    * ``all_pending=True`` — every inbox row in this workspace whose
      status is ``queued`` or ``failed``. Skips rows that already
      extracted successfully, so the user can't accidentally re-run
      every invoice.

    For each target row we:
      * flip ``inbox_messages.status`` back to ``queued`` (so the
        worker treats it as fresh work even if it had previously
        failed).
      * insert a new ``jobs`` row in state ``queued``.

    The background worker drains the queue and runs the pipeline. The
    UI polls the inbox after the click and watches the status chips
    transition queued → extracting → extracted.

    Returns ``{"queued": <count>, "skipped": <count>}``.
    """
    from business_layer.repositories import invoices as invoices_repo
    from business_layer.repositories import jobs as jobs_repo

    targets: list[InboxRowDc] = []

    if all_pending:
        rows = list_inbox(session, workspace_id=workspace_id, limit=500)
        targets = [r for r in rows if r.status in ("queued", "failed")]
    else:
        for mid in message_ids or []:
            row = inbox_repo.find_by_id_for_workspace(
                session, message_id=mid, workspace_id=workspace_id
            )
            if row is None:
                continue
            # Need an invoice id to create a job; create one if absent.
            inv_id = _find_invoice_for_inbox(session, message_id=row.id, workspace_id=workspace_id)
            targets.append(
                InboxRowDc(
                    id=row.id,
                    invoice_id=inv_id,
                    source_kind="upload",
                    sender=row.sender,
                    subject=row.subject,
                    received_at=row.received_at,
                    content_type=row.content_type,
                    status=row.status,
                    vendor_name=None,
                    total_amount_minor=None,
                    currency="INR",
                    failure_message=None,
                )
            )

    queued = 0
    skipped = 0
    for t in targets:
        if t.status == "extracted" and not all_pending:
            # Re-extract on demand for a single row IS allowed (useful
            # when the user has changed something), but not in bulk.
            pass
        if t.invoice_id is None:
            invoice = invoices_repo.create_pending(
                session, workspace_id=workspace_id, inbox_message_id=t.id
            )
            invoice_id_for_job = invoice.id
        else:
            invoice_id_for_job = t.invoice_id

        inbox_repo.update_status(session, message_id=t.id, status="queued")
        jobs_repo.create(
            session,
            workspace_id=workspace_id,
            inbox_message_id=t.id,
            invoice_id=invoice_id_for_job,
        )
        queued += 1

    skipped = max(0, len(message_ids or []) - queued) if not all_pending else 0
    return {"queued": queued, "skipped": skipped}


def _find_invoice_for_inbox(  # type: ignore[no-untyped-def]
    session: Session, *, message_id: str, workspace_id: str
) -> str | None:
    from sqlalchemy import desc as _desc
    from sqlalchemy import select as _select

    from business_layer.db.tables import invoices as t_inv

    row = session.execute(
        _select(t_inv.c.id)
        .where(t_inv.c.inbox_message_id == message_id, t_inv.c.workspace_id == workspace_id)
        .order_by(_desc(t_inv.c.created_at))
        .limit(1)
    ).first()
    return row.id if row else None


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
