"""Thin service around the ``sources`` row that represents a Gmail connection.

Exists to keep ``routes/oauth.py`` layer-clean — routes mustn't import
``repositories.*`` or ``db.*`` directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.orm import Session

from business_layer.db.tables import sources as t_sources
from business_layer.repositories import events as events_repo
from business_layer.repositories import sources as sources_repo

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GmailConnectResult:
    source_id: str
    was_new: bool


def upsert_connection(
    session: Session,
    *,
    workspace_id: str,
    user_id: str,
    encrypted_refresh_token: bytes,
) -> GmailConnectResult:
    """Persist a Gmail connection — creates the source row if absent.

    Records the connect event too. Caller (the OAuth callback) has
    already performed state-check + code-exchange + encryption.
    """
    existing = sources_repo.find_by_workspace_and_kind(
        session, workspace_id=workspace_id, kind="gmail"
    )
    if existing is None:
        src = sources_repo.create(
            session,
            workspace_id=workspace_id,
            kind="gmail",
            label="Gmail",
            status="connected",
            default_extraction_mode="instant",
        )
        session.execute(
            update(t_sources)
            .where(t_sources.c.id == src.id)
            .values(credentials_encrypted=encrypted_refresh_token)
        )
        was_new = True
        source_id = src.id
    else:
        session.execute(
            update(t_sources)
            .where(t_sources.c.id == existing.id)
            .values(
                status="connected",
                credentials_encrypted=encrypted_refresh_token,
            )
        )
        was_new = False
        source_id = existing.id

    events_repo.append(
        session,
        action="source.connected",
        workspace_id=workspace_id,
        actor_user_id=user_id,
        target_type="source",
        target_id=source_id,
        metadata={"kind": "gmail"},
    )
    return GmailConnectResult(source_id=source_id, was_new=was_new)


def disconnect(
    session: Session,
    *,
    workspace_id: str,
    user_id: str,
) -> str:
    """Return ``'disconnected'`` or ``'not_connected'``. Idempotent."""
    existing = sources_repo.find_by_workspace_and_kind(
        session, workspace_id=workspace_id, kind="gmail"
    )
    if existing is None:
        return "not_connected"
    session.execute(
        update(t_sources)
        .where(t_sources.c.id == existing.id)
        .values(status="disconnected", credentials_encrypted=None)
    )
    events_repo.append(
        session,
        action="source.disconnected",
        workspace_id=workspace_id,
        actor_user_id=user_id,
        target_type="source",
        target_id=existing.id,
        metadata={"kind": "gmail"},
    )
    return "disconnected"
