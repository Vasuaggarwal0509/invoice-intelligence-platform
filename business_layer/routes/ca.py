"""CA-persona dashboard routes.

Every route here depends on :func:`current_ca_context_dep` which
raises ``AuthorizationError(403)`` if the session isn't a CA user.
Cross-persona defence — a business-role session on a CA route is
denied at the dep layer, never reaches the service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from business_layer.errors import AuthorizationError
from business_layer.models.ca import (
    CaClientInvoiceListResponse,
    CaClientInvoicePublic,
    CaClientListResponse,
    CaClientPublic,
)
from business_layer.models.invoice import InvoiceDetailCa
from business_layer.services import UserRow, WorkspaceRow, ca_service, storage

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/ca", tags=["ca-dashboard"])


def current_ca_context_dep(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
) -> tuple[UserRow, WorkspaceRow]:
    """Narrow current_context to CA role only.

    Business-persona sessions → 403. Unauthenticated → 401 (from the
    upstream dep). This is the cross-persona IDOR gate.
    """
    user, workspace = ctx
    if user.role != "ca":
        raise AuthorizationError("this endpoint is for CA accounts only")
    return user, workspace


@router.get("/clients", response_model=CaClientListResponse)
def list_clients(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_ca_context_dep),
    session=Depends(session_dep),
) -> CaClientListResponse:
    """Every business workspace that has linked this CA + rollup metrics."""
    _, ca_ws = ctx
    rows = ca_service.list_clients(session, ca_workspace_gstin=ca_ws.gstin)
    return CaClientListResponse(
        items=[
            CaClientPublic(
                workspace_id=r.workspace_id,
                name=r.name,
                gstin=r.gstin,
                invoice_count=r.invoice_count,
                total_spend_minor=r.total_spend_minor,
                open_flags=r.open_flags,
            )
            for r in rows
        ]
    )


@router.get(
    "/clients/{business_workspace_id}/invoices",
    response_model=CaClientInvoiceListResponse,
)
def list_client_invoices(
    business_workspace_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_ca_context_dep),
    session=Depends(session_dep),
) -> CaClientInvoiceListResponse:
    """Invoices for one client, newest first. 404 if this CA isn't linked."""
    _, ca_ws = ctx
    rows = ca_service.list_client_invoices(
        session,
        ca_workspace_gstin=ca_ws.gstin,
        business_workspace_id=business_workspace_id,
        limit=limit,
        offset=offset,
    )
    return CaClientInvoiceListResponse(
        items=[
            CaClientInvoicePublic(
                invoice_id=r.invoice_id,
                vendor_name=r.vendor_name,
                invoice_no=r.invoice_no,
                invoice_date=r.invoice_date,
                total_amount_minor=r.total_amount_minor,
                currency=r.currency,
                status=r.status,
                failing_rules=r.failing_rules,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.get(
    "/clients/{business_workspace_id}/invoices/{invoice_id}",
    response_model=InvoiceDetailCa,
)
def get_client_invoice_detail(
    business_workspace_id: str,
    invoice_id: str,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_ca_context_dep),
    session=Depends(session_dep),
) -> InvoiceDetailCa:
    """Full CA-persona invoice detail: summary + every rule + raw pipeline JSON."""
    _, ca_ws = ctx
    return ca_service.get_client_invoice_detail(
        session,
        ca_workspace_gstin=ca_ws.gstin,
        business_workspace_id=business_workspace_id,
        invoice_id=invoice_id,
    )


@router.get("/clients/{business_workspace_id}/invoices/{invoice_id}/image")
def get_client_invoice_image(
    business_workspace_id: str,
    invoice_id: str,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_ca_context_dep),
    session=Depends(session_dep),
) -> Response:
    """Serve the invoice image bytes to a linked CA.

    The business-scoped ``/api/invoices/{id}/image`` would 404 because
    the CA's session workspace doesn't match the invoice's workspace.
    Here we apply the CA-linkage gate instead — same shape, different
    authorisation rule.
    """
    _, ca_ws = ctx
    storage_key, content_type, filename = ca_service.get_client_invoice_image_blob(
        session,
        ca_workspace_gstin=ca_ws.gstin,
        business_workspace_id=business_workspace_id,
        invoice_id=invoice_id,
    )
    return FileResponse(
        path=storage.blob_path(storage_key),
        media_type=content_type,
        filename=filename,
    )
