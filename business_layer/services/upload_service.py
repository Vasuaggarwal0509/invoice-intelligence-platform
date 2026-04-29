"""Upload service — bytes in, queued extraction job out.

One public function: :func:`ingest_upload`. Steps (all in one
transaction):

1. Size check (cap from settings).
2. Content-type sniff by magic bytes (never trust the header).
3. SHA-256 → dedup lookup per workspace (idempotent upload).
4. Store blob on disk under ``data/blobs/{workspace_id}/...``.
5. Insert ``inbox_messages`` (status='queued').
6. Insert ``invoices`` skeleton row (status='pending').
7. Insert ``jobs`` row (state='queued', stage='full').
8. Append ``events`` audit row.

Returns the inbox_message + invoice ids so the caller can redirect
the user to the detail page while extraction runs in the background.

Raises:
    ValidationError: Empty upload, oversized, unknown content-type.
    ConflictError: Upload duplicated an existing inbox row (returned
        with the existing ids so the frontend can gracefully jump to
        the already-known invoice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.config import get_settings
from business_layer.errors import ValidationError
from business_layer.repositories import events as events_repo
from business_layer.repositories import inbox_messages as inbox_repo
from business_layer.repositories import invoices as invoices_repo
from business_layer.repositories import jobs as jobs_repo
from business_layer.repositories import sources as sources_repo
from business_layer.services import storage

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestResult:
    """Return value of :func:`ingest_upload`."""

    inbox_message_id: str
    invoice_id: str
    job_id: str
    was_duplicate: bool


def ingest_upload(
    session: Session,
    *,
    workspace_id: str,
    user_id: str,
    filename: str | None,
    data: bytes,
) -> IngestResult:
    """Ingest a single upload. See module docstring for full contract."""
    settings = get_settings()

    # (1) empty + size checks — before any IO.
    if not data:
        raise ValidationError("upload is empty")
    if len(data) > settings.upload_max_bytes:
        raise ValidationError(
            f"upload exceeds limit of {settings.upload_max_bytes} bytes",
            context={"size": len(data), "limit": settings.upload_max_bytes},
        )

    # (2) content-type sniff. Never trust the caller-supplied type —
    # browsers and proxies both mislabel frequently.
    sniffed = storage.sniff_content_type(data)
    if sniffed is None:
        raise ValidationError(
            "unsupported file type",
            context={"filename_hint": filename},
        )

    # (3) dedup by (workspace, sha256).
    sha = storage.compute_sha256(data)
    existing = inbox_repo.find_by_workspace_and_sha(
        session, workspace_id=workspace_id, file_sha256=sha
    )
    if existing is not None:
        # Locate the associated invoice + most-recent job and return
        # them as the ingest result. Treated as success, not conflict —
        # idempotent uploads are a feature (user mashes the button twice).
        inv = _find_invoice_for_message(session, existing.id, workspace_id)
        if inv is None:
            # Invoice was never created (race window) — create it now.
            inv_row = invoices_repo.create_pending(
                session,
                workspace_id=workspace_id,
                inbox_message_id=existing.id,
            )
            inv_id = inv_row.id
        else:
            inv_id = inv
        job = jobs_repo.create(
            session,
            workspace_id=workspace_id,
            inbox_message_id=existing.id,
            invoice_id=inv_id,
        )
        return IngestResult(
            inbox_message_id=existing.id,
            invoice_id=inv_id,
            job_id=job.id,
            was_duplicate=True,
        )

    # (4) store the blob on disk. Done BEFORE DB writes so the blob
    # is present for the worker — a partial transaction that didn't
    # commit leaves an orphaned blob but no dangling DB reference.
    storage_key, _ = storage.store_blob(
        workspace_id=workspace_id,
        data=data,
        content_type=sniffed,
    )

    # (5–7) one transaction: source + inbox + invoice + job.
    source = sources_repo.get_or_create_upload_source(session, workspace_id=workspace_id)
    inbox = inbox_repo.create(
        session,
        workspace_id=workspace_id,
        source_id=source.id,
        sender=None,
        subject=filename,
        content_type=sniffed,
        file_storage_key=storage_key,
        file_size_bytes=len(data),
        file_sha256=sha,
        status="queued",
    )
    invoice = invoices_repo.create_pending(
        session,
        workspace_id=workspace_id,
        inbox_message_id=inbox.id,
    )
    job = jobs_repo.create(
        session,
        workspace_id=workspace_id,
        inbox_message_id=inbox.id,
        invoice_id=invoice.id,
    )

    # (8) audit trail. No PII — just ids + size + type.
    events_repo.append(
        session,
        action="invoice.uploaded",
        workspace_id=workspace_id,
        actor_user_id=user_id,
        target_type="invoice",
        target_id=invoice.id,
        metadata={
            "size_bytes": len(data),
            "content_type": sniffed,
            "source": "upload",
        },
    )
    _log.info(
        "upload.ingested",
        extra={
            "workspace_id": workspace_id,
            "invoice_id": invoice.id,
            "inbox_message_id": inbox.id,
            "size_bytes": len(data),
        },
    )

    return IngestResult(
        inbox_message_id=inbox.id,
        invoice_id=invoice.id,
        job_id=job.id,
        was_duplicate=False,
    )


def _find_invoice_for_message(
    session: Session,
    inbox_message_id: str,
    workspace_id: str,
) -> str | None:
    """Helper: most-recent invoice id for the given inbox_message (workspace-scoped)."""
    # Kept local to avoid a broader repository API just for one dedup branch.
    from sqlalchemy import desc, select

    from business_layer.db.tables import invoices as t_invoices

    row = session.execute(
        select(t_invoices.c.id)
        .where(
            t_invoices.c.inbox_message_id == inbox_message_id,
            t_invoices.c.workspace_id == workspace_id,
        )
        .order_by(desc(t_invoices.c.created_at))
        .limit(1)
    ).first()
    return row.id if row else None
