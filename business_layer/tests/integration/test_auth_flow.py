"""End-to-end auth flow via TestClient.

Covers the Sprint 1 gate:
  * Phone + OTP signup creates a user + workspace.
  * /api/auth/me returns identity after OTP verify.
  * Logout clears the session cookie and revokes the row.
  * Logging back in with the same phone returns is_new_user=False.

OTP extraction: the dev path logs the code to the structured logger
via :mod:`business_layer.routes.auth`. We capture stdout/logging to
read the code during tests instead of mocking the OTP module — keeps
the path exercised identical to production.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager

import pytest

PHONE_A = "+919000000001"
PHONE_B = "+919000000002"


@contextmanager
def _capture_otp(caplog: pytest.LogCaptureFixture):
    """Activate a log level + filter to snarf the DEV_OTP_ISSUED line."""
    caplog.set_level(logging.INFO, logger="business_layer.routes.auth")
    yield caplog


def _extract_otp_for(phone: str, caplog: pytest.LogCaptureFixture) -> str:
    """Return the OTP plaintext logged for ``phone`` during this test.

    Scans `caplog.records` for our dev-mode signal line and returns the
    last match (the most recently issued OTP).
    """
    pattern = re.compile(rf"DEV_OTP_ISSUED phone={re.escape(phone)} code=(\d{{6}})")
    for rec in reversed(caplog.records):
        msg = rec.getMessage()
        m = pattern.search(msg)
        if m:
            return m.group(1)
    raise AssertionError(f"DEV_OTP_ISSUED log line for phone={phone} not captured")


class TestSignupLoginLogoutFlow:
    """The Sprint 1 gate — signup, confirm, logout, log back in."""

    def test_signup_creates_user_and_workspace(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        with _capture_otp(caplog):
            # Step 1 — request an OTP for a brand-new phone.
            r1 = test_client.post("/api/auth/otp/request", json={"phone": PHONE_A})
            assert r1.status_code == 200
            assert r1.json() == {"status": "sent"}

            code = _extract_otp_for(PHONE_A, caplog)

            # Step 2 — verify with the code and provide a display name (signup path).
            r2 = test_client.post(
                "/api/auth/otp/verify",
                json={"phone": PHONE_A, "code": code, "display_name": "Acme Hardware"},
            )
            assert r2.status_code == 200, r2.text

        body = r2.json()
        assert body["is_new_user"] is True
        assert body["user"]["role"] == "business"
        assert body["user"]["phone"] == PHONE_A
        assert body["user"]["display_name"] == "Acme Hardware"
        assert body["workspace"]["name"] == "Acme Hardware"
        assert body["workspace"]["default_extraction_mode"] == "instant"

        # A session cookie must have been set.
        assert "bl_session" in r2.cookies

        # /api/auth/me should now work in the same client (cookies persist).
        r3 = test_client.get("/api/auth/me")
        assert r3.status_code == 200
        me = r3.json()
        assert me["user"]["id"] == body["user"]["id"]
        assert me["workspace"]["id"] == body["workspace"]["id"]

    def test_me_unauthenticated_returns_401(self, test_client) -> None:  # type: ignore[no-untyped-def]
        r = test_client.get("/api/auth/me")
        assert r.status_code == 401
        assert r.json()["code"] == "authentication_failed"

    def test_logout_then_me_returns_401(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        with _capture_otp(caplog):
            test_client.post("/api/auth/otp/request", json={"phone": PHONE_A})
            code = _extract_otp_for(PHONE_A, caplog)
            test_client.post(
                "/api/auth/otp/verify",
                json={"phone": PHONE_A, "code": code, "display_name": "Acme"},
            )

        assert test_client.get("/api/auth/me").status_code == 200

        logout = test_client.post("/api/auth/logout", json={})
        assert logout.status_code == 200
        # cookie is cleared server-side (Set-Cookie with empty value)
        assert "bl_session" in logout.headers.get("set-cookie", "").lower()

        # TestClient keeps cookies across requests; after delete_cookie
        # the cookie is present in jar but with empty value — /me sees
        # an invalid session token and returns 401.
        r_after = test_client.get("/api/auth/me")
        assert r_after.status_code == 401

    def test_second_login_is_not_a_new_user(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        # First signup.
        with _capture_otp(caplog):
            test_client.post("/api/auth/otp/request", json={"phone": PHONE_A})
            code_1 = _extract_otp_for(PHONE_A, caplog)
            r1 = test_client.post(
                "/api/auth/otp/verify",
                json={"phone": PHONE_A, "code": code_1, "display_name": "Acme"},
            )
        assert r1.status_code == 200
        assert r1.json()["is_new_user"] is True
        test_client.post("/api/auth/logout", json={})
        caplog.clear()

        # Second login — same phone, no display_name, is_new_user=False.
        with _capture_otp(caplog):
            test_client.post("/api/auth/otp/request", json={"phone": PHONE_A})
            code_2 = _extract_otp_for(PHONE_A, caplog)
            r2 = test_client.post(
                "/api/auth/otp/verify",
                json={"phone": PHONE_A, "code": code_2},
            )
        assert r2.status_code == 200, r2.text
        assert r2.json()["is_new_user"] is False

    def test_signup_without_display_name_rejected(
        self, test_client, caplog: pytest.LogCaptureFixture
    ) -> None:  # type: ignore[no-untyped-def]
        with _capture_otp(caplog):
            test_client.post("/api/auth/otp/request", json={"phone": PHONE_B})
            code = _extract_otp_for(PHONE_B, caplog)
            r = test_client.post(
                "/api/auth/otp/verify",
                json={"phone": PHONE_B, "code": code},  # no display_name
            )
        assert r.status_code == 400
        assert r.json()["code"] == "business_rule_violated"
