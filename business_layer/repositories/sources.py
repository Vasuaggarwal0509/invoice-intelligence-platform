"""sources table queries.

Sprint 2 wires only the ``upload`` kind — real Gmail / Outlook / WA
connectors arrive via the ``ingestion/*`` branch. The upload source is
auto-provisioned on first file upload so the inbox has a non-null
``source_id`` for every row (less NULL to check downstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from business_layer.db.tables import sources

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class SourceRow:
    id: str
    workspace_id: str
    kind: str
    label: str | None
    status: str
    default_extraction_mode: str
    last_polled_at: int | None
    created_at: int


def _row_to_dc(row: Any) -> SourceRow:
    return SourceRow(
        id=row.id,
        workspace_id=row.workspace_id,
        kind=row.kind,
        label=row.label,
        status=row.status,
        default_extraction_mode=row.default_extraction_mode,
        last_polled_at=row.last_polled_at,
        created_at=row.created_at,
    )


def find_by_workspace_and_kind(
    session: Session,
    *,
    workspace_id: str,
    kind: str,
) -> SourceRow | None:
    row = session.execute(
        select(sources).where(
            sources.c.workspace_id == workspace_id,
            sources.c.kind == kind,
        )
    ).first()
    return _row_to_dc(row) if row else None


def list_by_workspace(session: Session, *, workspace_id: str) -> list[SourceRow]:
    rows = session.execute(select(sources).where(sources.c.workspace_id == workspace_id)).all()
    return [_row_to_dc(r) for r in rows]


def create(
    session: Session,
    *,
    workspace_id: str,
    kind: str,
    label: str | None,
    status: str,
    default_extraction_mode: str,
) -> SourceRow:
    sid = new_id()
    session.execute(
        insert(sources).values(
            id=sid,
            workspace_id=workspace_id,
            kind=kind,
            label=label,
            status=status,
            default_extraction_mode=default_extraction_mode,
            credentials_encrypted=None,
            last_polled_at=None,
            created_at=now_ms(),
        )
    )
    row = session.execute(select(sources).where(sources.c.id == sid)).first()
    assert row is not None
    return _row_to_dc(row)


def get_or_create_upload_source(
    session: Session,
    *,
    workspace_id: str,
    default_extraction_mode: str = "instant",
) -> SourceRow:
    """Return the workspace's 'upload' source, creating it if absent."""
    existing = find_by_workspace_and_kind(session, workspace_id=workspace_id, kind="upload")
    if existing is not None:
        return existing
    return create(
        session,
        workspace_id=workspace_id,
        kind="upload",
        label="Manual upload",
        status="connected",
        default_extraction_mode=default_extraction_mode,
    )
