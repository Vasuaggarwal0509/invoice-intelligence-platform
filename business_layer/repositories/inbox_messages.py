"""inbox_messages table queries.

One row per *arrived* file (upload, email attachment, WhatsApp media,
forwarded). May or may not turn into an ``invoices`` row depending on
extraction outcome — the split lets the inbox viewer show queued /
ignored / failed items that pure invoice rows can't represent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, insert, select, update
from sqlalchemy.orm import Session

from business_layer.db.tables import inbox_messages

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class InboxMessageRow:
    id: str
    workspace_id: str
    source_id: str | None
    external_id: str | None
    sender: str | None
    subject: str | None
    received_at: int
    content_type: str
    file_storage_key: str
    file_size_bytes: int
    file_sha256: str
    status: str
    ignored_reason: str | None
    created_at: int


def _row_to_dc(row: Any) -> InboxMessageRow:
    return InboxMessageRow(
        id=row.id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        external_id=row.external_id,
        sender=row.sender,
        subject=row.subject,
        received_at=row.received_at,
        content_type=row.content_type,
        file_storage_key=row.file_storage_key,
        file_size_bytes=row.file_size_bytes,
        file_sha256=row.file_sha256,
        status=row.status,
        ignored_reason=row.ignored_reason,
        created_at=row.created_at,
    )


def find_by_workspace_and_sha(
    session: Session,
    *,
    workspace_id: str,
    file_sha256: str,
) -> InboxMessageRow | None:
    """Used for dedup — same file uploaded twice returns the existing row."""
    row = session.execute(
        select(inbox_messages).where(
            inbox_messages.c.workspace_id == workspace_id,
            inbox_messages.c.file_sha256 == file_sha256,
        )
    ).first()
    return _row_to_dc(row) if row else None


def find_by_id_for_workspace(
    session: Session,
    *,
    message_id: str,
    workspace_id: str,
) -> InboxMessageRow | None:
    """Scoped lookup — prevents cross-workspace reads (IDOR defence)."""
    row = session.execute(
        select(inbox_messages).where(
            inbox_messages.c.id == message_id,
            inbox_messages.c.workspace_id == workspace_id,
        )
    ).first()
    return _row_to_dc(row) if row else None


def list_by_workspace(
    session: Session,
    *,
    workspace_id: str,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> list[InboxMessageRow]:
    """Return messages in reverse chronological order (newest first)."""
    stmt = (
        select(inbox_messages)
        .where(inbox_messages.c.workspace_id == workspace_id)
        .order_by(desc(inbox_messages.c.received_at))
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(inbox_messages.c.status == status)
    rows = session.execute(stmt).all()
    return [_row_to_dc(r) for r in rows]


def create(
    session: Session,
    *,
    workspace_id: str,
    source_id: str,
    sender: str | None,
    subject: str | None,
    content_type: str,
    file_storage_key: str,
    file_size_bytes: int,
    file_sha256: str,
    status: str = "queued",
    external_id: str | None = None,
) -> InboxMessageRow:
    mid = new_id()
    now = now_ms()
    session.execute(
        insert(inbox_messages).values(
            id=mid,
            workspace_id=workspace_id,
            source_id=source_id,
            external_id=external_id,
            sender=sender,
            subject=subject,
            received_at=now,
            content_type=content_type,
            file_storage_key=file_storage_key,
            file_size_bytes=file_size_bytes,
            file_sha256=file_sha256,
            status=status,
            ignored_reason=None,
            created_at=now,
        )
    )
    row = session.execute(select(inbox_messages).where(inbox_messages.c.id == mid)).first()
    assert row is not None
    return _row_to_dc(row)


def update_status(
    session: Session,
    *,
    message_id: str,
    status: str,
    ignored_reason: str | None = None,
) -> None:
    values: dict[str, Any] = {"status": status}
    if ignored_reason is not None:
        values["ignored_reason"] = ignored_reason
    session.execute(
        update(inbox_messages).where(inbox_messages.c.id == message_id).values(**values)
    )
