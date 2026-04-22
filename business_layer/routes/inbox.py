"""Inbox routes — list, mark-ignored."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from business_layer.models.inbox import InboxListResponse, InboxRow
from business_layer.services import UserRow, WorkspaceRow
from business_layer.services import inbox_service

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


def _dc_to_row(dc, invoice_id_by_msg: dict[str, str]) -> InboxRow:  # type: ignore[no-untyped-def]
    return InboxRow(
        id=dc.id,
        invoice_id=dc.invoice_id,
        source_kind=dc.source_kind,  # type: ignore[arg-type]
        sender=dc.sender,
        subject=dc.subject,
        received_at=dc.received_at,
        content_type=dc.content_type,
        status=dc.status,  # type: ignore[arg-type]
        vendor_name=dc.vendor_name,
        total_amount_minor=dc.total_amount_minor,
        currency=dc.currency,
    )


@router.get("", response_model=InboxListResponse)
def list_inbox(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> InboxListResponse:
    """List inbox rows for the caller's workspace.

    Rows are newest-first. Optional ``status`` filter narrows to one
    state ('queued','extracting','extracted','failed','ignored').
    """
    _, workspace = ctx
    items = inbox_service.list_inbox(
        session,
        workspace_id=workspace.id,
        limit=limit,
        offset=offset,
        status=status,
    )
    total = inbox_service.count_inbox(session, workspace_id=workspace.id)
    return InboxListResponse(
        items=[_dc_to_row(i, {}) for i in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/{message_id}/ignore")
def post_ignore(
    message_id: str,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> dict[str, str]:
    """Mark an inbox row as ``ignored`` — won't trigger extraction."""
    _, workspace = ctx
    inbox_service.mark_ignored(
        session,
        workspace_id=workspace.id,
        message_id=message_id,
        reason="user_marked",
    )
    return {"status": "ignored"}
