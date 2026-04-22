"""Source routes — list connected ingestion sources.

Sprint 2 ships read-only. Sprint 4 wires the real OAuth connect
flows; the UI can already render "Gmail: not connected" etc. from
whatever rows exist.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from business_layer.services import UserRow, WorkspaceRow, sources_service

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceRowPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["gmail", "outlook", "whatsapp", "upload", "folder"]
    label: str | None
    status: Literal["stub", "connected", "error", "disconnected"]
    default_extraction_mode: Literal["instant", "scheduled", "manual"]


class SourceListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[SourceRowPublic]


@router.get("", response_model=SourceListResponse)
def list_sources(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> SourceListResponse:
    """Return every source connected to the caller's workspace."""
    _, workspace = ctx
    rows = sources_service.list_for_workspace(session, workspace_id=workspace.id)
    return SourceListResponse(
        items=[
            SourceRowPublic(
                id=r.id,
                kind=r.kind,  # type: ignore[arg-type]
                label=r.label,
                status=r.status,  # type: ignore[arg-type]
                default_extraction_mode=r.default_extraction_mode,  # type: ignore[arg-type]
            )
            for r in rows
        ]
    )
