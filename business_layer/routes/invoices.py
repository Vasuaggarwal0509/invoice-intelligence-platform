"""Invoice routes — detail + image serving.

Every route here verifies workspace ownership BEFORE doing anything
else. Cross-workspace access returns 404 (not 403) — smallest possible
existence leak.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response

from business_layer.models.invoice import InvoiceDetailBusiness
from business_layer.services import UserRow, WorkspaceRow, invoice_service, storage

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


@router.get("/{invoice_id}", response_model=InvoiceDetailBusiness)
def get_detail(
    invoice_id: str,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> InvoiceDetailBusiness:
    """Business-persona detail: plain-language summary + failing findings only."""
    _, workspace = ctx
    return invoice_service.get_business_detail(
        session, workspace_id=workspace.id, invoice_id=invoice_id
    )


@router.get("/{invoice_id}/image")
def get_image(
    invoice_id: str,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> Response:
    """Stream the original uploaded bytes for an invoice.

    The workspace check happens inside
    :func:`invoice_service.get_blob_for_image_route`. A cross-workspace
    request gets a 404 before the filesystem is ever touched.
    """
    _, workspace = ctx
    storage_key, content_type, filename = invoice_service.get_blob_for_image_route(
        session, workspace_id=workspace.id, invoice_id=invoice_id
    )
    path = storage.blob_path(storage_key)
    return FileResponse(
        path=path,
        media_type=content_type,
        filename=filename,
    )
