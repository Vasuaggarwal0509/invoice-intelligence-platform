"""invoices table queries.

One invoices row per successfully-extracted inbox_message. Fields
populated lazily as extraction runs — an invoice can exist with
``status='pending'`` and almost every other column NULL until the
extraction runner fills them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, insert, select, update
from sqlalchemy.orm import Session

from business_layer.db.tables import invoices

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class InvoiceRow:
    id: str
    workspace_id: str
    inbox_message_id: str
    vendor_name: str | None
    client_name: str | None
    client_gstin: str | None
    seller_gstin: str | None
    invoice_no: str | None
    invoice_date: str | None
    total_amount_minor: int | None
    currency: str
    status: str
    created_at: int
    approved_at: int | None
    approved_by_user_id: str | None


def _row_to_dc(row: Any) -> InvoiceRow:
    return InvoiceRow(
        id=row.id,
        workspace_id=row.workspace_id,
        inbox_message_id=row.inbox_message_id,
        vendor_name=row.vendor_name,
        client_name=row.client_name,
        client_gstin=row.client_gstin,
        seller_gstin=row.seller_gstin,
        invoice_no=row.invoice_no,
        invoice_date=row.invoice_date,
        total_amount_minor=row.total_amount_minor,
        currency=row.currency,
        status=row.status,
        created_at=row.created_at,
        approved_at=row.approved_at,
        approved_by_user_id=row.approved_by_user_id,
    )


def find_by_id_for_workspace(
    session: Session,
    *,
    invoice_id: str,
    workspace_id: str,
) -> InvoiceRow | None:
    """Scoped lookup — IDOR defence lives in the WHERE clause."""
    row = session.execute(
        select(invoices).where(
            invoices.c.id == invoice_id,
            invoices.c.workspace_id == workspace_id,
        )
    ).first()
    return _row_to_dc(row) if row else None


def list_by_workspace(
    session: Session,
    *,
    workspace_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[InvoiceRow]:
    rows = session.execute(
        select(invoices)
        .where(invoices.c.workspace_id == workspace_id)
        .order_by(desc(invoices.c.created_at))
        .limit(limit)
        .offset(offset)
    ).all()
    return [_row_to_dc(r) for r in rows]


def create_pending(
    session: Session,
    *,
    workspace_id: str,
    inbox_message_id: str,
) -> InvoiceRow:
    """Create a skeleton row before extraction runs.

    All content fields start NULL; the extraction runner fills them in
    via :func:`update_extracted_fields`.
    """
    iid = new_id()
    session.execute(
        insert(invoices).values(
            id=iid,
            workspace_id=workspace_id,
            inbox_message_id=inbox_message_id,
            currency="INR",
            status="pending",
            created_at=now_ms(),
        )
    )
    row = session.execute(select(invoices).where(invoices.c.id == iid)).first()
    assert row is not None
    return _row_to_dc(row)


def update_extracted_fields(
    session: Session,
    *,
    invoice_id: str,
    vendor_name: str | None = None,
    client_name: str | None = None,
    client_gstin: str | None = None,
    seller_gstin: str | None = None,
    invoice_no: str | None = None,
    invoice_date: str | None = None,
    total_amount_minor: int | None = None,
) -> None:
    """Write post-extraction fields back to the invoice row.

    Only non-None args are applied — so re-running extraction with a
    partial result doesn't clobber previously-good fields. The
    extraction runner composes these values from ExtractionResult.
    """
    values: dict[str, Any] = {}
    for k, v in [
        ("vendor_name", vendor_name),
        ("client_name", client_name),
        ("client_gstin", client_gstin),
        ("seller_gstin", seller_gstin),
        ("invoice_no", invoice_no),
        ("invoice_date", invoice_date),
        ("total_amount_minor", total_amount_minor),
    ]:
        if v is not None:
            values[k] = v
    if not values:
        return
    session.execute(update(invoices).where(invoices.c.id == invoice_id).values(**values))
