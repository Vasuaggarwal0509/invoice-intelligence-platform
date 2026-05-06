"""Inbox routes — list, mark-ignored, manual extract trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from business_layer.models.inbox import InboxListResponse, InboxRow
from business_layer.services import UserRow, WorkspaceRow, inbox_service

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class ExtractRequest(BaseModel):
    """Body of ``POST /api/inbox/extract``.

    Caller specifies EITHER a list of message_ids OR all_pending=True.
    Sending both is fine — message_ids wins; sending neither is a no-op
    that returns ``{"queued": 0}``.
    """

    model_config = ConfigDict(extra="forbid")

    message_ids: list[str] | None = None
    all_pending: bool = False


class ExtractResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    queued: int
    skipped: int


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
        failure_message=dc.failure_message,
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


@router.post("/extract", response_model=ExtractResponse)
def post_extract(
    body: ExtractRequest,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> ExtractResponse:
    """Manually queue inbox rows for extraction.

    Either ``message_ids`` (selected rows) or ``all_pending=True`` (every
    queued/failed row in this workspace). The background worker will
    pick the queued jobs up — typically within a second.
    """
    _, workspace = ctx
    result = inbox_service.trigger_extract(
        session,
        workspace_id=workspace.id,
        message_ids=body.message_ids,
        all_pending=body.all_pending,
    )
    return ExtractResponse(queued=result["queued"], skipped=result["skipped"])
