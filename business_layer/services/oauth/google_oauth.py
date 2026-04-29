"""Google OAuth 2.0 server-side flow for Gmail connection.

Multi-tenant web-app pattern:
  1. ``/api/oauth/google/start`` → build auth URL with signed ``state`` +
     PKCE challenge, redirect browser to accounts.google.com.
  2. User consents. Google redirects back to
     ``/api/oauth/google/callback?code=...&state=...``.
  3. Verify state (CSRF defence), verify PKCE, exchange code for
     refresh_token + access_token.
  4. Encrypt refresh_token + AES-GCM-binding to workspace_id; persist
     on ``sources.credentials_encrypted``.

The ``state`` parameter is an itsdangerous-signed URL-safe token
carrying ``user_id``, ``workspace_id``, ``code_verifier``, and a
timestamp. Signature + TTL check on callback.

Offline mode:
  * ``access_type='offline'`` + ``prompt='consent'`` forces Google to
    hand back a refresh_token even on a repeat authorization from the
    same user (without ``prompt='consent'`` Google may return only an
    access token on subsequent consents).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets as _stdlib_secrets
import time
from dataclasses import dataclass
from pathlib import Path

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from business_layer.config import get_settings
from business_layer.errors import AuthorizationError, DependencyError
from business_layer.security import encryption as enc

_log = logging.getLogger(__name__)

# Scope: read-only access to Gmail (messages, labels, attachments).
# Never request broader scopes — any upgrade forces users to re-consent
# and Google's "restricted" scope review applies.
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

# State TTL — if a user takes longer than this between start and
# callback we invalidate. Protects against replay of stale URLs.
_STATE_TTL_SECONDS = 600  # 10 min

_STATE_SALT = "google-oauth-state-v1"


@dataclass(frozen=True)
class AuthUrlBundle:
    """What :func:`build_auth_url` returns for the route to act on."""

    auth_url: str
    state_token: str  # for logging / audit; already embedded in auth_url


@dataclass(frozen=True)
class ExchangeResult:
    """Decoded outcome of the code exchange."""

    refresh_token: str  # plaintext — caller encrypts before persisting
    access_token: str  # short-lived; we discard (rebuilt per-use)
    scopes: list[str]
    email_address: str | None = None  # if we can deduce it (usually not)


# ---------- client-file gating + loading -------------------------------


def is_configured() -> bool:
    """Return True iff a real (non-dummy) OAuth client file is in place.

    Cheap check — reads just enough to see if the client_id starts
    with the dummy prefix. Routes call this to 404 gracefully when
    Gmail ingestion isn't wired up.
    """
    settings = get_settings()
    path = Path(settings.google_oauth_client_file)
    if not path.exists():
        return False
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    web = doc.get("web") or doc.get("installed") or {}
    cid = str(web.get("client_id", ""))
    return bool(cid) and not cid.startswith("dummy-")


def _client_config() -> dict:
    """Return the dict passed to ``Flow.from_client_config``.

    We pass a dict rather than from_client_secrets_file so tests can
    inject a fake configuration without touching the filesystem.
    """
    settings = get_settings()
    path = Path(settings.google_oauth_client_file)
    if not path.exists():
        raise DependencyError(
            "Gmail integration not configured (OAuth client file missing)",
            context={"file": str(path)},
        )
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- PKCE helpers -----------------------------------------------


def _new_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256.

    ``code_verifier`` is a 64-byte URL-safe random string; we send the
    SHA-256 (base64url, no padding) as the challenge and keep the
    verifier in the signed state token for the callback to echo.
    """
    verifier = _stdlib_secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# ---------- state token (CSRF) -----------------------------------------


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(
        secret_key=settings.secret_key.get_secret_value(),
        salt=_STATE_SALT,
    )


def _encode_state(*, user_id: str, workspace_id: str, code_verifier: str) -> str:
    return _serializer().dumps(
        {
            "u": user_id,
            "w": workspace_id,
            "v": code_verifier,
            "t": int(time.time()),
        }
    )


def _decode_state(token: str) -> dict:
    try:
        return _serializer().loads(token, max_age=_STATE_TTL_SECONDS)
    except SignatureExpired as exc:
        raise AuthorizationError("oauth state expired, please retry") from exc
    except BadSignature as exc:
        raise AuthorizationError("oauth state invalid") from exc


# ---------- auth URL + code exchange -----------------------------------


def build_auth_url(*, user_id: str, workspace_id: str) -> AuthUrlBundle:
    """Construct the Google consent URL for a specific workspace.

    The returned URL goes straight into a 302 redirect. Once Google
    redirects back to the callback, :func:`exchange_code` finishes
    the flow.
    """
    # Import lazily so the service module imports cleanly even when
    # the google_auth_oauthlib package isn't installed (tests can mock
    # this function out without pulling in the whole library).
    from google_auth_oauthlib.flow import Flow

    settings = get_settings()
    verifier, challenge = _new_pkce_pair()
    state = _encode_state(
        user_id=user_id,
        workspace_id=workspace_id,
        code_verifier=verifier,
    )

    flow = Flow.from_client_config(
        _client_config(),
        scopes=[GMAIL_READONLY_SCOPE],
        redirect_uri=settings.google_oauth_redirect_uri,
    )
    flow.code_verifier = verifier  # type: ignore[attr-defined]

    auth_url, _ = flow.authorization_url(
        access_type="offline",  # ensures refresh_token is issued
        include_granted_scopes="true",
        prompt="consent",  # forces refresh_token on re-consent
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    return AuthUrlBundle(auth_url=auth_url, state_token=state)


@dataclass(frozen=True)
class DecodedState:
    user_id: str
    workspace_id: str
    code_verifier: str


def decode_state(state: str) -> DecodedState:
    """Parse the signed state string the callback receives.

    Raises :class:`AuthorizationError` on bad/expired signatures.
    """
    payload = _decode_state(state)
    return DecodedState(
        user_id=payload["u"],
        workspace_id=payload["w"],
        code_verifier=payload["v"],
    )


def exchange_code(*, code: str, code_verifier: str) -> ExchangeResult:
    """Turn an authorization code into tokens.

    Raises :class:`DependencyError` if Google returns a non-success
    response or the token payload is malformed.
    """
    from google_auth_oauthlib.flow import Flow

    settings = get_settings()
    flow = Flow.from_client_config(
        _client_config(),
        scopes=[GMAIL_READONLY_SCOPE],
        redirect_uri=settings.google_oauth_redirect_uri,
    )
    flow.code_verifier = code_verifier  # type: ignore[attr-defined]

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        _log.warning("gmail.oauth.exchange_failed", extra={"err": str(exc)})
        raise DependencyError("google token exchange failed") from exc

    creds = flow.credentials
    if not getattr(creds, "refresh_token", None):
        raise DependencyError(
            "google did not return a refresh_token — "
            "ensure the Google app has prompt=consent + access_type=offline"
        )
    return ExchangeResult(
        refresh_token=creds.refresh_token,
        access_token=creds.token,
        scopes=list(creds.scopes or []),
        email_address=None,
    )


# ---------- encrypt / decrypt the refresh token ------------------------


def encrypt_refresh_token(*, refresh_token: str, workspace_id: str) -> bytes:
    """AES-GCM-encrypt with ``workspace_id`` as AAD.

    AAD binds the ciphertext to the workspace — a stolen blob cannot
    be decrypted in the context of a different workspace row.
    """
    return enc.encrypt(
        refresh_token.encode("utf-8"),
        associated_data=workspace_id.encode("utf-8"),
    )


def decrypt_refresh_token(*, blob: bytes, workspace_id: str) -> str:
    """Inverse of :func:`encrypt_refresh_token`.

    Raises :class:`cryptography.exceptions.InvalidTag` on tamper /
    wrong workspace / wrong key — caller should treat as "source
    disconnected" and stop polling.
    """
    return enc.decrypt(blob, associated_data=workspace_id.encode("utf-8")).decode("utf-8")


# ---------- runtime credential rehydration -----------------------------


def build_credentials_from_refresh_token(*, refresh_token: str):  # type: ignore[no-untyped-def]
    """Return a ``google.oauth2.credentials.Credentials`` for use with the Gmail API.

    The connector calls this each poll tick. access_token auto-refreshes
    via the Google library's built-in handler when it expires.
    """
    from google.oauth2.credentials import Credentials

    client_cfg = _client_config()
    web = client_cfg.get("web") or client_cfg.get("installed") or {}
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=web.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=web.get("client_id"),
        client_secret=web.get("client_secret"),
        scopes=[GMAIL_READONLY_SCOPE],
    )
