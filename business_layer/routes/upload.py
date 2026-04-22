"""Upload route — multipart/form-data entry point to the extraction pipeline."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, UploadFile

from business_layer.models.inbox import UploadResponse
from business_layer.services import UserRow, WorkspaceRow
from business_layer.services.upload_service import ingest_upload

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/upload", tags=["upload"])

_log = logging.getLogger(__name__)


@router.post("", response_model=UploadResponse, status_code=201)
async def post_upload(
    file: UploadFile = File(...),
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> UploadResponse:
    """Accept a single file upload; return the ids + the queued job.

    The service layer enforces size + content-type + dedup. Workspace
    scoping comes from the authenticated context.
    """
    user, workspace = ctx
    raw = await file.read()
    result = ingest_upload(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        filename=file.filename,
        data=raw,
    )
    return UploadResponse(
        inbox_message_id=result.inbox_message_id,
        invoice_id=result.invoice_id,
        job_id=result.job_id,
        was_duplicate=result.was_duplicate,
        status="queued",
    )
