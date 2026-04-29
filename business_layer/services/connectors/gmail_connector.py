"""Gmail → upload_service bridge.

Single entrypoint :func:`pull_new_attachments`. Called by the
``gmail_poller`` worker (one call per connected source per tick).

Flow per tick:
  1. Decrypt the source's stored refresh_token.
  2. Build Gmail API credentials + service.
  3. Construct a search query from the runtime config's keywords +
     the source's ``last_polled_at`` cursor.
  4. Paginate message list; for each message fetch + filter
     attachments by our supported content-types.
  5. Hand each attachment's bytes to ``upload_service.ingest_upload``
     (which dedups by sha256 — idempotent across retries).
  6. Update ``sources.last_polled_at`` so next tick is incremental.

Failure modes:
  * `invalid_grant` from Google → set source status to 'disconnected'
    (user revoked consent). The poller stops polling that source.
  * transient network / quota → log + skip this tick; try again next.
  * malformed message — log + skip that one message; keep going.
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass

from sqlalchemy import update as _sa_update
from sqlalchemy.orm import Session

from business_layer.config import get_runtime_config
from business_layer.db.tables import sources as t_sources
from business_layer.errors import DependencyError
from business_layer.repositories.sources import SourceRow
from business_layer.services.oauth import google_oauth
from business_layer.services.upload_service import ingest_upload

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PullStats:
    """Returned from one poll tick for observability."""

    messages_scanned: int
    attachments_ingested: int
    attachments_skipped: int
    marked_disconnected: bool


# ---------- public entrypoint ------------------------------------------


def pull_new_attachments(
    session: Session,
    *,
    source: SourceRow,
    user_id: str,
) -> PullStats:
    """One poll cycle for one connected Gmail source.

    ``source`` is the DB row for a ``kind='gmail'`` source that's
    ``status='connected'`` and has ``credentials_encrypted`` populated.

    All DB writes use the caller-provided ``session``. Transaction
    scope is the caller's — the worker commits after a successful
    return and rolls back on exception.
    """
    cfg = get_runtime_config().email_ingestion

    # ----- 1. decrypt the refresh token --------------------------------
    blob_row = session.execute(t_sources.select().where(t_sources.c.id == source.id)).first()
    if blob_row is None or not blob_row.credentials_encrypted:
        _log.info("gmail.pull.no_creds", extra={"source_id": source.id})
        return PullStats(0, 0, 0, False)
    try:
        refresh_token = google_oauth.decrypt_refresh_token(
            blob=bytes(blob_row.credentials_encrypted),
            workspace_id=source.workspace_id,
        )
    except Exception:
        _log.exception("gmail.pull.decrypt_failed", extra={"source_id": source.id})
        _mark_disconnected(session, source_id=source.id)
        return PullStats(0, 0, 0, True)

    # ----- 2. build credentials + service ------------------------------
    try:
        creds = google_oauth.build_credentials_from_refresh_token(
            refresh_token=refresh_token,
        )
        service = _build_gmail_service(creds)
    except Exception as exc:
        _log.exception("gmail.pull.service_build_failed", extra={"source_id": source.id})
        raise DependencyError("gmail service build failed") from exc

    # ----- 3. construct search query -----------------------------------
    query = _build_search_query(
        cfg=cfg,
        since_ms=source.last_polled_at,
    )
    _log.info(
        "gmail.pull.start",
        extra={
            "source_id": source.id,
            "workspace_id": source.workspace_id,
            "query": query,
        },
    )

    # ----- 4. paginate + fetch -----------------------------------------
    scanned = 0
    ingested = 0
    skipped = 0
    next_page_token = None
    try:
        for _ in range(10):  # hard cap: 10 pages × ~100 msgs = 1000/tick
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(100, cfg.max_messages_per_poll - scanned),
                    pageToken=next_page_token,
                )
                .execute()
            )
            messages = response.get("messages", []) or []
            for msg_meta in messages:
                if scanned >= cfg.max_messages_per_poll:
                    break
                scanned += 1
                try:
                    this_ingested, this_skipped = _process_message(
                        session,
                        service=service,
                        message_id=msg_meta["id"],
                        source=source,
                        user_id=user_id,
                        max_attachments=cfg.max_attachments_per_message,
                        supported_types=cfg.supported_content_types,
                    )
                    ingested += this_ingested
                    skipped += this_skipped
                except Exception:
                    _log.exception(
                        "gmail.pull.message_failed",
                        extra={"message_id": msg_meta["id"]},
                    )
                    skipped += 1

            next_page_token = response.get("nextPageToken")
            if not next_page_token or scanned >= cfg.max_messages_per_poll:
                break
    except _InvalidGrant:
        _mark_disconnected(session, source_id=source.id)
        return PullStats(scanned, ingested, skipped, True)
    except Exception as exc:
        _log.exception("gmail.pull.list_failed", extra={"source_id": source.id})
        raise DependencyError("gmail message list failed") from exc

    # ----- 5. stamp last_polled_at -------------------------------------
    _mark_last_polled(session, source_id=source.id)

    _log.info(
        "gmail.pull.done",
        extra={
            "source_id": source.id,
            "scanned": scanned,
            "ingested": ingested,
            "skipped": skipped,
        },
    )
    return PullStats(scanned, ingested, skipped, False)


# ---------- per-message logic ------------------------------------------


def _process_message(
    session: Session,
    *,
    service,  # type: ignore[no-untyped-def]
    message_id: str,
    source: SourceRow,
    user_id: str,
    max_attachments: int,
    supported_types: tuple[str, ...],
) -> tuple[int, int]:
    """Download + ingest every supported attachment on one message.

    Returns ``(ingested_count, skipped_count)`` — caller sums these.
    """
    # ``format='full'`` returns headers + body + attachment metadata
    # without triggering per-attachment HTTP calls yet.
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender = headers.get("from")
    subject = headers.get("subject")

    ingested = 0
    skipped = 0

    # Breadth-first walk of MIME parts to find attachments.
    parts = _flatten_parts(msg.get("payload") or {})
    attach_count = 0
    for part in parts:
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        filename = part.get("filename")
        mime = part.get("mimeType")
        if not attachment_id or not filename:
            continue  # inline content, not a downloadable attachment
        if mime not in supported_types:
            skipped += 1
            continue
        if attach_count >= max_attachments:
            skipped += 1
            break
        attach_count += 1

        # Fetch the actual bytes.
        att = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
        raw_b64 = att.get("data")
        if not raw_b64:
            skipped += 1
            continue
        raw = base64.urlsafe_b64decode(raw_b64)

        # Dedup by sha256 is handled by upload_service.ingest_upload.
        # If we've already seen this attachment (same sha256 in this
        # workspace), it returns was_duplicate=True and we just skip.
        try:
            result = ingest_upload(
                session,
                workspace_id=source.workspace_id,
                user_id=user_id,
                filename=filename,
                data=raw,
            )
        except Exception:
            _log.exception(
                "gmail.pull.ingest_failed",
                extra={"message_id": message_id, "filename": filename},
            )
            skipped += 1
            continue
        if result.was_duplicate:
            skipped += 1
        else:
            ingested += 1

            # Annotate the inbox_message with Gmail context so the UI
            # can show "from john@acme.com" and admins can trace.
            from business_layer.db.tables import inbox_messages as t_inbox_write

            session.execute(
                _sa_update(t_inbox_write)
                .where(t_inbox_write.c.id == result.inbox_message_id)
                .values(
                    source_id=source.id,
                    sender=sender,
                    subject=subject,
                    external_id=f"gmail:{message_id}:{attachment_id}",
                )
            )
    return ingested, skipped


# ---------- helpers -----------------------------------------------------


def _flatten_parts(part: dict) -> list[dict]:
    """Depth-first flatten of a MIME tree — attachments may nest."""
    out: list[dict] = [part]
    for child in part.get("parts", []) or []:
        out.extend(_flatten_parts(child))
    return out


def _build_search_query(*, cfg, since_ms: int | None) -> str:  # type: ignore[no-untyped-def]
    """Compose a Gmail search query from config + cursor.

    Examples::

        has:attachment subject:(invoice OR bill) newer_than:30d -in:spam -in:trash
        has:attachment subject:(...) after:1710000000
    """
    parts: list[str] = ["has:attachment"]

    if cfg.has_keyword_filter():
        # Gmail subject: operator accepts parens + OR.
        keywords = " OR ".join(kw.replace('"', "") for kw in cfg.subject_keywords)
        parts.append(f"subject:({keywords})")

    # Cursor: prefer incremental (after:) if we have one; else use the
    # config backfill_days as a bounded first-run window.
    if since_ms:
        # Gmail's `after:` takes a unix timestamp (seconds).
        parts.append(f"after:{int(since_ms // 1000)}")
    else:
        parts.append(f"newer_than:{cfg.backfill_days}d")

    parts.append("-in:spam")
    parts.append("-in:trash")
    return " ".join(parts)


def _build_gmail_service(creds):  # type: ignore[no-untyped-def]
    """Construct the Gmail v1 service client.

    Kept as a separate function so tests can monkeypatch it to return
    a stub without pulling in the real discovery cache.
    """
    from googleapiclient.discovery import build

    # ``cache_discovery=False`` avoids a disk-cache writer that logs
    # scary warnings on first run; the discovery doc is cached in
    # memory for the service's lifetime anyway.
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------- source-status mutations ------------------------------------


class _InvalidGrant(Exception):
    """Raised when Google responds with a revoked-refresh-token error."""


def _mark_disconnected(session: Session, *, source_id: str) -> None:
    from sqlalchemy import update as _upd

    session.execute(
        _upd(t_sources).where(t_sources.c.id == source_id).values(status="disconnected")
    )


def _mark_last_polled(session: Session, *, source_id: str) -> None:
    from sqlalchemy import update as _upd

    session.execute(
        _upd(t_sources)
        .where(t_sources.c.id == source_id)
        .values(last_polled_at=int(time.time() * 1000))
    )
