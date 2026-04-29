"""CA-persona dashboard service.

Top-level operations:
  * list_clients(ca_workspace) → each business linked to this CA + rollup metrics
  * list_client_invoices(ca_workspace, business_workspace_id) → the
    business's invoices, visible only to their linked CA.
  * get_client_invoice_detail(ca_workspace, ..., invoice_id) → full CA
    detail (pipeline JSON + every rule finding, not just failures).

Also exposes the business-side "link your CA" operation:
  * link_ca(business_workspace, ca_gstin) — verifies the GSTIN matches
    a real CA workspace, then writes ``workspaces.ca_gstin``.

Every function enforces workspace scoping inline so a route that
forgot to authorize fails closed rather than open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.errors import (
    BusinessRuleError,
    NotFoundError,
    ValidationError,
)
from business_layer.repositories import ca_queries
from business_layer.repositories import workspaces as workspaces_repo
from business_layer.repositories.ca_queries import CaClientInvoiceRow, CaClientRow
from business_layer.services import invoice_service
from business_layer.services.invoice_service import get_ca_detail

_log = logging.getLogger(__name__)


# ---------- CA dashboard reads ----------------------------------------


def list_clients(session: Session, *, ca_workspace_gstin: str | None) -> list[CaClientRow]:
    """Return every business workspace linked to this CA + aggregates.

    A CA whose own workspace has no GSTIN can't have clients — we
    return empty, not raise, so the UI degrades to an empty state.
    """
    if not ca_workspace_gstin:
        return []
    return ca_queries.list_clients(session, ca_gstin=ca_workspace_gstin)


def list_client_invoices(
    session: Session,
    *,
    ca_workspace_gstin: str | None,
    business_workspace_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[CaClientInvoiceRow]:
    """List invoices for one client. 404 if the CA isn't authorised.

    The authorisation check is also baked into the SQL query (WHERE
    ca_gstin = ?). We do the existence check first to distinguish
    "business doesn't exist" from "business exists but not yours" —
    returning 404 in both cases (same leakage defence as the
    per-workspace IDOR pattern).
    """
    if not ca_workspace_gstin:
        raise NotFoundError("client not found")
    if not ca_queries.is_ca_authorised_for_workspace(
        session,
        ca_gstin=ca_workspace_gstin,
        workspace_id=business_workspace_id,
    ):
        raise NotFoundError("client not found")

    return ca_queries.list_client_invoices(
        session,
        ca_gstin=ca_workspace_gstin,
        workspace_id=business_workspace_id,
        limit=limit,
        offset=offset,
    )


def get_client_invoice_detail(
    session: Session,
    *,
    ca_workspace_gstin: str | None,
    business_workspace_id: str,
    invoice_id: str,
):  # returns InvoiceDetailCa
    """CA-persona full invoice detail — delegates to existing invoice_service.

    Same auth gate pattern: must be the CA's own linked client.
    """
    if not ca_workspace_gstin:
        raise NotFoundError("invoice not found")
    if not ca_queries.is_ca_authorised_for_workspace(
        session,
        ca_gstin=ca_workspace_gstin,
        workspace_id=business_workspace_id,
    ):
        raise NotFoundError("invoice not found")
    return get_ca_detail(
        session,
        workspace_id=business_workspace_id,
        invoice_id=invoice_id,
    )


def get_client_invoice_image_blob(
    session: Session,
    *,
    ca_workspace_gstin: str | None,
    business_workspace_id: str,
    invoice_id: str,
) -> tuple[str, str, str]:
    """Return ``(storage_key, content_type, filename)`` for an invoice image.

    Gated on the CA ↔ business linkage. Raises NotFound if the CA
    isn't authorised (same signal as 'invoice absent' — IDOR defence).
    The route layer hands the storage_key to ``FileResponse``.
    """
    if not ca_workspace_gstin:
        raise NotFoundError("invoice not found")
    if not ca_queries.is_ca_authorised_for_workspace(
        session,
        ca_gstin=ca_workspace_gstin,
        workspace_id=business_workspace_id,
    ):
        raise NotFoundError("invoice not found")
    return invoice_service.get_blob_for_image_route(
        session,
        workspace_id=business_workspace_id,
        invoice_id=invoice_id,
    )


# ---------- business-side: "link your CA" ------------------------------


@dataclass(frozen=True)
class LinkedCaSummary:
    ca_workspace_id: str
    ca_name: str
    ca_gstin: str


def link_ca_for_business(
    session: Session,
    *,
    business_workspace_id: str,
    ca_gstin: str,
) -> LinkedCaSummary:
    """Business nominates a CA. Validates the GSTIN exists + belongs to a CA.

    Raises:
        NotFoundError: no workspace with that GSTIN.
        BusinessRuleError: that GSTIN belongs to a non-CA workspace.
    """
    if not ca_gstin or len(ca_gstin) != 15:
        raise ValidationError("GSTIN must be 15 characters")

    ca_ws = workspaces_repo.find_by_gstin(session, gstin=ca_gstin)
    if ca_ws is None:
        raise NotFoundError("no CA registered with that GSTIN")

    # Resolve the owner user to verify they're role='ca'.
    from business_layer.repositories import users as users_repo

    owner = users_repo.find_by_id(session, ca_ws.owner_user_id)
    if owner is None or owner.role != "ca":
        raise BusinessRuleError(
            "that GSTIN is registered but not as a CA workspace",
        )

    workspaces_repo.set_ca_gstin(
        session,
        workspace_id=business_workspace_id,
        ca_gstin=ca_gstin,
    )

    from business_layer.repositories import events as events_repo

    events_repo.append(
        session,
        action="business.linked_ca",
        workspace_id=business_workspace_id,
        target_type="workspace",
        target_id=ca_ws.id,
    )
    _log.info(
        "ca.link.set",
        extra={
            "business_workspace_id": business_workspace_id,
            "ca_workspace_id": ca_ws.id,
        },
    )
    return LinkedCaSummary(
        ca_workspace_id=ca_ws.id,
        ca_name=ca_ws.name,
        ca_gstin=ca_gstin,
    )


def unlink_ca_for_business(
    session: Session,
    *,
    business_workspace_id: str,
) -> None:
    """Remove the CA pairing for a business — idempotent."""
    workspaces_repo.set_ca_gstin(
        session,
        workspace_id=business_workspace_id,
        ca_gstin=None,
    )
    from business_layer.repositories import events as events_repo

    events_repo.append(
        session,
        action="business.unlinked_ca",
        workspace_id=business_workspace_id,
    )
