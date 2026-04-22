"""workspaces table queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from business_layer.db.tables import workspaces

from ._ids import new_id, now_ms


@dataclass(frozen=True)
class WorkspaceRow:
    id: str
    owner_user_id: str
    name: str
    gstin: str | None
    created_via: str
    tier: str
    status: str
    region: str | None
    default_extraction_mode: str
    created_at: int


def _row_to_dc(row: Any) -> WorkspaceRow:
    return WorkspaceRow(
        id=row.id,
        owner_user_id=row.owner_user_id,
        name=row.name,
        gstin=row.gstin,
        created_via=row.created_via,
        tier=row.tier,
        status=row.status,
        region=row.region,
        default_extraction_mode=row.default_extraction_mode,
        created_at=row.created_at,
    )


def find_by_owner(session: Session, *, owner_user_id: str) -> WorkspaceRow | None:
    """Return the workspace owned by ``owner_user_id``, or None.

    v1 schema enforces ``UNIQUE(owner_user_id)`` — at most one row.
    """
    row = session.execute(
        select(workspaces).where(workspaces.c.owner_user_id == owner_user_id)
    ).first()
    return _row_to_dc(row) if row else None


def find_by_id(session: Session, workspace_id: str) -> WorkspaceRow | None:
    row = session.execute(
        select(workspaces).where(workspaces.c.id == workspace_id)
    ).first()
    return _row_to_dc(row) if row else None


def create(
    session: Session,
    *,
    owner_user_id: str,
    name: str,
    gstin: str | None = None,
    created_via: str = "self_signup",
    default_extraction_mode: str = "instant",
) -> WorkspaceRow:
    """Create a workspace for a freshly-signed-up user."""
    wid = new_id()
    session.execute(
        insert(workspaces).values(
            id=wid,
            owner_user_id=owner_user_id,
            name=name,
            gstin=gstin,
            created_via=created_via,
            tier="free",
            status="active",
            default_extraction_mode=default_extraction_mode,
            created_at=now_ms(),
        )
    )
    row = find_by_id(session, wid)
    assert row is not None
    return row
