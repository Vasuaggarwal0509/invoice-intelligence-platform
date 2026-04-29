"""Invoice detail service.

Assembles an :class:`InvoiceDetailBusiness` (plain-language) or an
:class:`InvoiceDetailCa` (full breakdown). Sprint 2 implements the
business view; the CA entry point is defined for completeness + used
by Sprint 4's routes.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_layer.db.tables import inbox_messages as t_inbox
from business_layer.db.tables import sources as t_sources
from business_layer.errors import NotFoundError
from business_layer.models.invoice import (
    InvoiceDetailBusiness,
    InvoiceDetailCa,
    InvoiceSummary,
    ValidationFindingPublic,
)
from business_layer.repositories import inbox_messages as inbox_repo
from business_layer.repositories import invoices as invoices_repo
from business_layer.repositories import pipeline_runs as pipeline_runs_repo
from business_layer.repositories import validation_findings as findings_repo


def _summary(
    session: Session, *, workspace_id: str, invoice_id: str
) -> tuple[InvoiceSummary, list[ValidationFindingPublic]]:
    invoice = invoices_repo.find_by_id_for_workspace(
        session, invoice_id=invoice_id, workspace_id=workspace_id
    )
    if invoice is None:
        # Cross-workspace reads also return 404 by design — see IDOR note.
        raise NotFoundError("invoice not found")

    inbox = inbox_repo.find_by_id_for_workspace(
        session,
        message_id=invoice.inbox_message_id,
        workspace_id=workspace_id,
    )
    if inbox is None:
        # This would be a data bug — an invoice with no inbox message.
        # Surface as NotFound rather than a 500; the frontend can at
        # least show a clear message.
        raise NotFoundError("inbox message for invoice not found")

    # source.kind for the summary header. Left-join style lookup —
    # inline SQL kept here (simple join, not worth a repo method).
    source_kind = "upload"
    if inbox.source_id:
        row = session.execute(
            select(t_sources.c.kind).where(t_sources.c.id == inbox.source_id)
        ).first()
        if row:
            source_kind = row.kind

    findings_rows = findings_repo.list_for_invoice(
        session, invoice_id=invoice_id, workspace_id=workspace_id
    )
    findings_public = [
        ValidationFindingPublic(
            rule_name=f.rule_name,
            target=f.target,
            outcome=f.outcome,  # type: ignore[arg-type]
            reason=f.reason,
            expected=f.expected,
            observed=f.observed,
        )
        for f in findings_rows
    ]

    summary = InvoiceSummary(
        id=invoice.id,
        status=invoice.status,  # type: ignore[arg-type]
        vendor_name=invoice.vendor_name,
        invoice_no=invoice.invoice_no,
        invoice_date=invoice.invoice_date,
        total_amount_minor=invoice.total_amount_minor,
        currency=invoice.currency,
        source_kind=source_kind,
        received_at=inbox.received_at,
        extraction_status=inbox.status,  # type: ignore[arg-type]
        findings_summary={
            "pass": sum(1 for f in findings_public if f.outcome == "PASS"),
            "fail": sum(1 for f in findings_public if f.outcome == "FAIL"),
            "not_applicable": sum(1 for f in findings_public if f.outcome == "NOT_APPLICABLE"),
        },
        image_url=f"/api/invoices/{invoice.id}/image",
    )
    return summary, findings_public


def get_business_detail(
    session: Session, *, workspace_id: str, invoice_id: str
) -> InvoiceDetailBusiness:
    """Plain-language view — summary + failing findings only.

    Business owner doesn't care about PASS / NOT_APPLICABLE rows. The
    ones that matter are the ones the platform wants them to look at.
    """
    summary, findings = _summary(session, workspace_id=workspace_id, invoice_id=invoice_id)
    flags = [f for f in findings if f.outcome == "FAIL"]
    return InvoiceDetailBusiness(invoice=summary, flags=flags)


def get_ca_detail(session: Session, *, workspace_id: str, invoice_id: str) -> InvoiceDetailCa:
    """Full detail — every rule + raw pipeline JSON. Used by CA persona (Sprint 4)."""
    summary, findings = _summary(session, workspace_id=workspace_id, invoice_id=invoice_id)
    latest = pipeline_runs_repo.find_latest_for_invoice(
        session, invoice_id=invoice_id, workspace_id=workspace_id
    )

    def _load(raw: str | None):  # type: ignore[no-untyped-def]
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    return InvoiceDetailCa(
        invoice=summary,
        findings=findings,
        ocr_result=_load(latest.ocr_result_json) if latest else None,
        extraction_result=_load(latest.extraction_result_json) if latest else None,
        tables_result=_load(latest.tables_result_json) if latest else None,
        validation_result=_load(latest.validation_result_json) if latest else None,
        pipeline_version=latest.pipeline_version if latest else None,
        total_ms=latest.total_ms if latest else None,
    )


def get_blob_for_image_route(
    session: Session, *, workspace_id: str, invoice_id: str
) -> tuple[str, str, str]:
    """Return ``(storage_key, content_type, filename_hint)`` for serving the image.

    The route uses this to hand bytes to :class:`FileResponse`, with
    the workspace check already performed by the lookup.
    """
    invoice = invoices_repo.find_by_id_for_workspace(
        session, invoice_id=invoice_id, workspace_id=workspace_id
    )
    if invoice is None:
        raise NotFoundError("invoice not found")
    inbox_row = session.execute(
        select(
            t_inbox.c.file_storage_key,
            t_inbox.c.content_type,
            t_inbox.c.subject,
        ).where(
            t_inbox.c.id == invoice.inbox_message_id,
            t_inbox.c.workspace_id == workspace_id,
        )
    ).first()
    if inbox_row is None:
        raise NotFoundError("blob not found")
    return (
        inbox_row.file_storage_key,
        inbox_row.content_type,
        inbox_row.subject or "invoice",
    )
