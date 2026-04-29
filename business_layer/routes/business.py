"""Business persona dashboard routes.

Sprint 3 surface: ``GET /api/business/dashboard``. One endpoint packs
tiles + top-vendors + needs-review so the frontend renders without
a flash of partial data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from business_layer.errors import AuthorizationError
from business_layer.models.ca import BusinessLinkCaRequest, LinkedCaPublic
from business_layer.models.kpi import (
    DashboardPublic,
    KpiTilesPublic,
    NeedsReviewItemPublic,
    VendorTotalPublic,
)
from business_layer.services import UserRow, WorkspaceRow, ca_service
from business_layer.services.kpi_service import build_dashboard

from .deps import current_context_dep, session_dep

router = APIRouter(prefix="/api/business", tags=["business-dashboard"])


def _require_business(user: UserRow) -> None:
    """Cross-persona gate: CA accounts can't call business endpoints."""
    if user.role != "business":
        raise AuthorizationError("this endpoint is for business accounts only")


@router.get("/dashboard", response_model=DashboardPublic)
def get_dashboard(
    period: str = Query(default="this_month"),
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> DashboardPublic:
    """Full dashboard payload for the caller's workspace.

    ``period`` accepts ``'this_month'`` today; future periods degrade
    silently to this-month rather than 400.
    """
    user, workspace = ctx
    _require_business(user)
    payload = build_dashboard(session, workspace_id=workspace.id, period=period)
    return DashboardPublic(
        period_year=payload.period_year,
        period_month=payload.period_month,
        currency=payload.currency,
        tiles=KpiTilesPublic(
            invoices_this_month=payload.tiles.invoices_this_month,
            total_spend_minor=payload.tiles.total_spend_minor,
            itc_estimate_minor=payload.tiles.itc_estimate_minor,
            needs_review_count=payload.tiles.needs_review_count,
        ),
        top_vendors=[
            VendorTotalPublic(
                vendor_name=v.vendor_name,
                invoice_count=v.invoice_count,
                total_minor=v.total_minor,
            )
            for v in payload.top_vendors
        ],
        needs_review=[
            NeedsReviewItemPublic(
                invoice_id=i.invoice_id,
                vendor_name=i.vendor_name,
                invoice_no=i.invoice_no,
                invoice_date=i.invoice_date,
                total_minor=i.total_minor,
                created_at=i.created_at,
                failing_rules=i.failing_rules,
            )
            for i in payload.needs_review
        ],
    )


@router.post("/ca-link", response_model=LinkedCaPublic)
def post_link_ca(
    body: BusinessLinkCaRequest,
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> LinkedCaPublic:
    """Pair this business workspace with a CA firm by their GSTIN.

    404 if no CA workspace with that GSTIN exists.
    """
    user, workspace = ctx
    _require_business(user)
    summary = ca_service.link_ca_for_business(
        session,
        business_workspace_id=workspace.id,
        ca_gstin=body.ca_gstin,
    )
    return LinkedCaPublic(
        ca_workspace_id=summary.ca_workspace_id,
        ca_name=summary.ca_name,
        ca_gstin=summary.ca_gstin,
    )


@router.delete("/ca-link")
def delete_link_ca(
    ctx: tuple[UserRow, WorkspaceRow] = Depends(current_context_dep),
    session=Depends(session_dep),
) -> dict[str, str]:
    """Remove the CA pairing — idempotent."""
    user, workspace = ctx
    _require_business(user)
    ca_service.unlink_ca_for_business(session, business_workspace_id=workspace.id)
    return {"status": "unlinked"}
