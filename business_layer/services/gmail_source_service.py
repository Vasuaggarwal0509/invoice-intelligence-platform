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
    email_address: str | None = None,
) -> GmailConnectResult:
    """Persist a Gmail connection — creates the source row if absent.

    Records the connect event too. Caller (the OAuth callback) has
    already performed state-check + code-exchange + encryption.

    ``email_address`` (when known — fetched from Google's Gmail
    ``users().getProfile()`` during OAuth exchange) is stored as the
    source's ``label``. The dashboard renders "Gmail · <address>" so
    users see WHICH account they connected.
    """
    label = f"Gmail · {email_address}" if email_address else "Gmail"
    existing = sources_repo.find_by_workspace_and_kind(
        session, workspace_id=workspace_id, kind="gmail"
    )
    if existing is None:
        src = sources_repo.create(
            session,
            workspace_id=workspace_id,
            kind="gmail",
            label=label,
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
        # On reconnect the user might be authenticating a DIFFERENT
        # Gmail account than before (multi-account isn't supported in
        # v1, but this overwrites cleanly). Always refresh the label
        # to match the just-connected address.
        session.execute(
            update(t_sources)
            .where(t_sources.c.id == existing.id)
            .values(
                status="connected",
                label=label,
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


def fetch_now(
    session: Session,
    *,
    workspace_id: str,
    user_id: str,
):  # returns gmail_connector.PullStats
    """Trigger an immediate Gmail poll for this workspace's connected source.

    Synchronous — runs the same per-tick logic the background poller
    uses, but right now in the request thread. Returns the same
    ``PullStats`` (messages_scanned, attachments_ingested, etc.) so
    the route can show a "got N new invoices" toast.

    Crucially, this passes ``force_full_window=True`` to the
    connector — Fetch-now ignores the incremental cursor and scans
    the full ``backfill_days`` window. Reasons:
      * Users press the button expecting "find anything matching",
        not "find things since the last incremental tick" (their
        test email may have been sent BEFORE the cursor moved).
      * Re-scanning is safe: dedupe via SHA-256 in upload_service
        means already-ingested attachments are skipped.
      * The cursor stays untouched, so the background poller still
        does honest incremental work on the next tick.

    Raises:
        NotFoundError: no Gmail source on this workspace, or the
            source exists but is in 'disconnected' state.
    """
    from business_layer.errors import NotFoundError
    from business_layer.services.connectors import gmail_connector

    src = sources_repo.find_by_workspace_and_kind(session, workspace_id=workspace_id, kind="gmail")
    if src is None:
        raise NotFoundError("no gmail source connected — connect email first")
    if src.status != "connected":
        raise NotFoundError("gmail source is not connected — reconnect from the dashboard")

    events_repo.append(
        session,
        action="source.fetch_now",
        workspace_id=workspace_id,
        actor_user_id=user_id,
        target_type="source",
        target_id=src.id,
        metadata={"kind": "gmail"},
    )
    return gmail_connector.pull_new_attachments(
        session, source=src, user_id=user_id, force_full_window=True
    )


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
