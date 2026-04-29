"""Email-sprint tests — OAuth state CSRF + connector logic with mocked Gmail.

Uses monkeypatched Google APIs so no real credentials or network calls
are involved. Verifies:
  * OAuth routes 503 when the dummy client file is in place (expected
    default — no real creds committed).
  * State token signing + expiry rejects tampered callbacks.
  * Connector builds a correct Gmail search query from config.
  * Connector ingests attachments via the existing upload pipeline.
"""

from __future__ import annotations

import base64
import logging
import re
import struct
import zlib

import pytest

# ---------- helpers ---------------------------------------------------


def _tiny_png() -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    ihdr_chunk = _png_chunk(b"IHDR", ihdr)
    raw = (b"\x00" + b"\xff\xff\xff" * 2) * 2
    idat = _png_chunk(b"IDAT", zlib.compress(raw))
    iend = _png_chunk(b"IEND", b"")
    return sig + ihdr_chunk + idat + iend


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _otp_from_logs(phone: str, caplog: pytest.LogCaptureFixture) -> str:
    pat = re.compile(rf"DEV_OTP_ISSUED phone={re.escape(phone)} code=(\d{{6}})")
    for rec in reversed(caplog.records):
        m = pat.search(rec.getMessage())
        if m:
            return m.group(1)
    raise AssertionError("OTP not captured")


def _signup_business(test_client, phone: str, name: str, caplog: pytest.LogCaptureFixture) -> dict:
    caplog.set_level(logging.INFO, logger="business_layer.routes.auth")
    test_client.post("/api/auth/otp/request", json={"phone": phone})
    code = _otp_from_logs(phone, caplog)
    r = test_client.post(
        "/api/auth/otp/verify",
        json={"phone": phone, "code": code, "display_name": name},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------- OAuth route tests -----------------------------------------


class TestOauthRoutesDummyConfig:
    """With the dummy client file, start + callback degrade gracefully."""

    def test_start_503_when_dummy_config(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        _signup_business(test_client, "+919000003000", "Biz", caplog)
        r = test_client.get("/api/oauth/google/start", follow_redirects=False)
        # DependencyError → 502 per our handler; accept either 502 or 503
        assert r.status_code in (502, 503)

    def test_start_requires_auth(self, test_client) -> None:  # type: ignore[no-untyped-def]
        r = test_client.get("/api/oauth/google/start", follow_redirects=False)
        assert r.status_code == 401


class TestOauthStateSigning:
    """State token must be HMAC-verified and workspace-bound."""

    def test_tampered_state_rejected(self, test_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
        _signup_business(test_client, "+919000003001", "Biz", caplog)
        r = test_client.get(
            "/api/oauth/google/callback?code=abc&state=not-a-real-signature",
            follow_redirects=False,
        )
        assert r.status_code == 403

    def test_cross_session_state_rejected(
        self, test_client, caplog: pytest.LogCaptureFixture, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        # User A signs up and requests their state token.
        biz_a = _signup_business(test_client, "+919000003002", "A", caplog)
        from business_layer.services.oauth import google_oauth as go

        # Mint a state token targeted at user_a + workspace_a.
        state = go._encode_state(
            user_id=biz_a["user"]["id"],
            workspace_id=biz_a["workspace"]["id"],
            code_verifier="v",
        )

        # Log out, sign up as user B.
        test_client.post("/api/auth/logout", json={})
        test_client.cookies.clear()
        caplog.clear()
        _signup_business(test_client, "+919000003003", "B", caplog)

        # User B posts user A's state token + a code (code value is
        # irrelevant — the mismatch check fires before exchange).
        r = test_client.get(
            f"/api/oauth/google/callback?code=x&state={state}",
            follow_redirects=False,
        )
        assert r.status_code == 403


# ---------- Connector tests (mocked Gmail API) -------------------------


class FakeGmailService:
    """Minimal stand-in for the Gmail discovery client.

    Returns one message with one PNG attachment so we can assert the
    connector ingests it through upload_service.
    """

    def __init__(self) -> None:
        self._png = _tiny_png()
        self._png_b64 = base64.urlsafe_b64encode(self._png).decode("ascii")

    def users(self):
        return self

    def messages(self):
        return self

    def attachments(self):
        return self

    # messages.list()
    def list(self, *, userId, q, maxResults, pageToken):
        # Capture the query for test assertions.
        self._last_query = q

        class _R:
            def execute(_self):
                return {
                    "messages": [{"id": "msg-1"}],
                    "nextPageToken": None,
                }

        return _R()

    # messages.get()
    def get(self, **kwargs):
        if "messageId" in kwargs:

            class _AttR:
                def execute(_self):
                    return {"data": self._png_b64}

            _outer = self

            class _Ret:
                def execute(_self):
                    return {"data": _outer._png_b64}

            return _Ret()

        # The message.get path.
        class _R:
            def execute(_self):
                return {
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "vendor@example.com"},
                            {"name": "Subject", "value": "Invoice #42"},
                        ],
                        "parts": [
                            {
                                "mimeType": "image/png",
                                "filename": "invoice.png",
                                "body": {"attachmentId": "att-1"},
                            }
                        ],
                    }
                }

        return _R()


class TestGmailConnector:
    def test_pulls_and_ingests_attachment(
        self, test_client, caplog: pytest.LogCaptureFixture, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        from business_layer.services.connectors import gmail_connector

        # Sign up a business + create a Gmail source row directly.
        biz = _signup_business(test_client, "+919000003100", "Biz", caplog)
        ws_id = biz["workspace"]["id"]
        user_id = biz["user"]["id"]

        from sqlalchemy import update

        from business_layer.db import get_session
        from business_layer.db.tables import sources as t_sources
        from business_layer.repositories import sources as sources_repo
        from business_layer.services.oauth import google_oauth

        # Seed a Gmail source with a dummy encrypted refresh token.
        with get_session() as s:
            src = sources_repo.create(
                s,
                workspace_id=ws_id,
                kind="gmail",
                label="Gmail",
                status="connected",
                default_extraction_mode="instant",
            )
            blob = google_oauth.encrypt_refresh_token(
                refresh_token="fake-refresh-token",
                workspace_id=ws_id,
            )
            s.execute(
                update(t_sources).where(t_sources.c.id == src.id).values(credentials_encrypted=blob)
            )

        # Stub the Google API surface.
        fake_service = FakeGmailService()
        monkeypatch.setattr(
            "business_layer.services.connectors.gmail_connector._build_gmail_service",
            lambda creds: fake_service,
        )
        monkeypatch.setattr(
            "business_layer.services.oauth.google_oauth.build_credentials_from_refresh_token",
            lambda refresh_token: object(),
        )

        # Stub the extraction pipeline so ingest_upload doesn't try to
        # run OCR (the queued job is processed by the real worker; tests
        # don't drive it here).
        from extraction_layer.components.extraction.types import ExtractionResult
        from extraction_layer.components.ocr.types import OCRResult, PageSize
        from extraction_layer.components.tables.types import TableExtractionResult

        monkeypatch.setattr(
            "extraction_layer.backend.app.pipeline.PipelineRunner.run",
            lambda self, img: (
                OCRResult(
                    tokens=[],
                    lines=[],
                    page=PageSize(width=2, height=2),
                    backend="stub",
                    duration_ms=0.1,
                ),
                ExtractionResult(fields={}, extractor="stub", duration_ms=0.1),
                TableExtractionResult(items=[], extractor="stub", duration_ms=0.1),
                None,
            ),
        )
        import business_layer.services.extraction_runner as er

        er._pipeline_singleton = None

        # Run one poll tick.
        with get_session() as s:
            src_row = sources_repo.find_by_workspace_and_kind(s, workspace_id=ws_id, kind="gmail")
        with get_session() as s:
            stats = gmail_connector.pull_new_attachments(s, source=src_row, user_id=user_id)

        assert stats.messages_scanned == 1
        assert stats.attachments_ingested == 1
        assert stats.marked_disconnected is False

        # The search query should include our keyword filter.
        assert "has:attachment" in fake_service._last_query
        assert "subject:(" in fake_service._last_query

        # The inbox should now show the ingested message.
        r = test_client.get("/api/inbox")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["source_kind"] == "gmail"
        assert items[0]["sender"] == "vendor@example.com"
        assert items[0]["subject"] == "Invoice #42"


class TestRuntimeConfigQueryBuilder:
    """Search query respects the configured keyword list."""

    def test_query_has_subject_keywords(self) -> None:
        from business_layer.config import get_runtime_config
        from business_layer.services.connectors.gmail_connector import _build_search_query

        cfg = get_runtime_config().email_ingestion
        q = _build_search_query(cfg=cfg, since_ms=None)
        assert "has:attachment" in q
        assert "invoice" in q.lower()
        assert "-in:spam" in q
        assert "-in:trash" in q
        assert f"newer_than:{cfg.backfill_days}d" in q

    def test_query_uses_after_when_cursor_set(self) -> None:
        from business_layer.config import get_runtime_config
        from business_layer.services.connectors.gmail_connector import _build_search_query

        cfg = get_runtime_config().email_ingestion
        q = _build_search_query(cfg=cfg, since_ms=1_700_000_000_000)
        assert "after:1700000000" in q
        assert "newer_than" not in q
