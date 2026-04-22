"""Sources service — thin wrapper over the sources repository.

Exists so ``routes/sources.py`` doesn't import ``business_layer.repositories.*``
directly (layer rule). A real service layer is coming for the OAuth
connect / disconnect flows in Sprint 4; for Sprint 2 it just lists.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from business_layer.repositories import sources as sources_repo


@dataclass(frozen=True)
class SourcePublic:
    id: str
    kind: str
    label: str | None
    status: str
    default_extraction_mode: str


def list_for_workspace(session: Session, *, workspace_id: str) -> list[SourcePublic]:
    return [
        SourcePublic(
            id=r.id,
            kind=r.kind,
            label=r.label,
            status=r.status,
            default_extraction_mode=r.default_extraction_mode,
        )
        for r in sources_repo.list_by_workspace(session, workspace_id=workspace_id)
    ]
