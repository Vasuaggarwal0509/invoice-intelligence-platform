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
    force_full_window: bool = False,
) -> PullStats:
    """One poll cycle for one connected Gmail source.

    ``source`` is the DB row for a ``kind='gmail'`` source that's
    ``status='connected'`` and has ``credentials_encrypted`` populated.

    All DB writes use the caller-provided ``session``. Transaction
    scope is the caller's — the worker commits after a successful
    return and rolls back on exception.

    Args:
        force_full_window: When True, ignore the source's
            ``last_polled_at`` cursor and search the full backfill
            window (config: ``email_ingestion.backfill_days``). The
            user-facing "Fetch now" button uses this — users press
            it expecting "find anything that matches NOW", not "find
            things since my last incremental poll." Also skips
            updating ``last_polled_at``, so the background poller's
            cursor stays correct.

            False (default) is the background-poller behaviour:
            incremental ``after:<cursor>`` query, advance the cursor
            on success.

            Dedupe via the upload service's SHA-256 check is the
            same in both modes — a re-scanned attachment that's
            already in the DB is silently skipped.
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
    # Background poller (force_full_window=False):
    #   * incremental: after:<cursor> if cursor set, else newer_than:Nd
    #   * advances cursor on success
    # Fetch-now button (force_full_window=True):
    #   * NO date filter — scan whole inbox matching keywords/attachment
    #   * Why: Gmail's newer_than: filters by the email's Date: header,
    #     NOT received date. Forwarded old emails or messages from a
    #     clock-skewed sender have stale Date headers and get excluded
    #     by newer_than: even when they were received just now.
    #     SHA-256 dedup in upload_service makes re-scans safe; users
    #     pressing Fetch-now expect "find anything that matches now",
    #     not a time-window subset.
    cursor = None if force_full_window else source.last_polled_at
    query = _build_search_query(
        cfg=cfg,
        since_ms=cursor,
        unbounded=force_full_window,
    )
    _log.info(
        "gmail.pull.start force_full=%s query=%s",
        force_full_window,
        query,
        extra={
            "source_id": source.id,
            "workspace_id": source.workspace_id,
            "query": query,
            "force_full_window": force_full_window,
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
        # Detect Google's "Gmail API not enabled" / failedPrecondition
        # so the user gets a useful error in the UI instead of "gmail
        # message list failed". This is the #1 first-time setup bug.
        msg = "gmail message list failed"
        try:
            from googleapiclient.errors import HttpError

            if isinstance(exc, HttpError):
                # exc.error_details is a list of {message, domain, reason}
                # dicts when Google returns structured errors.
                details = getattr(exc, "error_details", None) or []
                reasons = [str(d.get("reason", "")) for d in details]
                if "failedPrecondition" in reasons or "SERVICE_DISABLED" in reasons:
                    msg = (
                        "Gmail API isn't enabled for this Google Cloud project. "
                        "Enable it at https://console.cloud.google.com/apis/library/gmail.googleapis.com "
                        "(make sure the project matches your OAuth client), wait ~1 min, retry."
                    )
                elif exc.resp.status == 403:
                    msg = (
                        "Gmail rejected the request (403). Most likely the user's account "
                        "has restricted Gmail API access (Google Workspace policy)."
                    )
                elif exc.resp.status == 429:
                    msg = "Gmail rate-limited us. Try again in a minute."
        except Exception:
            pass  # never let error-classification itself raise
        _log.exception("gmail.pull.list_failed", extra={"source_id": source.id})
        raise DependencyError(msg) from exc

    # ----- 5. stamp last_polled_at -------------------------------------
    # Skip the cursor-advance when we deliberately scanned the full
    # window. The background poller's incremental cursor must stay
    # honest — a Fetch-now click shouldn't make the next scheduled
    # tick miss messages between the old cursor and now.
    if not force_full_window:
        _mark_last_polled(session, source_id=source.id)

    _log.info(
        "gmail.pull.done scanned=%d ingested=%d skipped=%d cursor_advanced=%s",
        scanned,
        ingested,
        skipped,
        not force_full_window,
        extra={
            "source_id": source.id,
            "scanned": scanned,
            "ingested": ingested,
            "skipped": skipped,
            "cursor_advanced": not force_full_window,
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


def _build_search_query(  # type: ignore[no-untyped-def]
    *,
    cfg,
    since_ms: int | None,
    unbounded: bool = False,
) -> str:
    """Compose a Gmail search query from config + cursor.

    Args:
        since_ms: Unix-millisecond cursor. When set, query uses
            ``after:<unix_seconds>``. Used by the background poller
            for incremental scans.
        unbounded: When True, OMIT the date filter entirely (no
            ``after:``, no ``newer_than:``). Used by the Fetch-now
            button.

            Why we need an "unbounded" mode: Gmail's ``newer_than:``
            operator filters by the email's ``Date:`` header (sender's
            claimed send time), NOT by the received timestamp. Emails
            sent from a clock-skewed device, or forwards that preserve
            an old original Date, get excluded by ``newer_than:30d``
            even when they arrived in the inbox today. The user
            pressing Fetch-now wants any matching email; SHA-256
            dedup in upload_service prevents re-ingestion of already-
            seen attachments.

    Examples::

        # Background poller, first run (no cursor):
        has:attachment subject:(invoice OR bill) newer_than:30d -in:spam -in:trash

        # Background poller, incremental:
        has:attachment subject:(...) after:1710000000 -in:spam -in:trash

        # Fetch-now button (unbounded):
        has:attachment subject:(invoice OR bill) -in:spam -in:trash
    """
    parts: list[str] = ["has:attachment"]

    if cfg.has_keyword_filter():
        # Gmail subject: operator accepts parens + OR. Multi-word
        # keywords MUST be double-quoted so Gmail treats them as
        # phrases — without quoting, "tax invoice" parses as
        # (tax AND invoice) and the surrounding OR-list can match
        # unexpectedly few emails. Single-word keywords are wrapped
        # too for uniformity (no harm; Gmail accepts "invoice" same
        # as invoice). Internal double-quotes are stripped to keep
        # the query syntax valid.
        def _quote(kw: str) -> str:
            cleaned = kw.replace('"', "").strip()
            return f'"{cleaned}"' if cleaned else ""

        terms = [_quote(kw) for kw in cfg.subject_keywords if kw.strip()]
        if terms:
            parts.append(f"subject:({' OR '.join(terms)})")

    if since_ms:
        # Cursor wins over backfill window — Gmail's `after:` takes a
        # unix timestamp (seconds).
        parts.append(f"after:{int(since_ms // 1000)}")
    elif not unbounded:
        # First-run / no cursor + bounded mode → bounded backfill.
        parts.append(f"newer_than:{cfg.backfill_days}d")
    # else: unbounded — no date filter at all.

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
