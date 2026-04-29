"""Typed settings loaded from the process environment.

All configuration that varies between dev / CI / prod lives here. No
module reads ``os.environ`` directly — that centralises the surface,
lets us fail loud at startup when a required secret is missing, and
gives tests a single override point via
:func:`get_settings.cache_clear` + env monkey-patching.

Usage::

    from business_layer.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url)

The accessor is LRU-cached so ``get_settings()`` is effectively a
singleton, but the cache is cheap to clear in tests.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the business_layer/ package root. Used to resolve
# default paths (SQLite file, migrations, static assets) regardless of
# which CWD the process was started from.
_HERE = Path(__file__).resolve().parent.parent  # .../business_layer/


class Settings(BaseSettings):
    """Process-wide configuration.

    All fields must be overridable via environment variables with the
    ``PLATFORM_`` prefix — e.g. ``PLATFORM_SECRET_KEY=...``. Nested
    fields (none yet) would use ``__`` as a delimiter.

    Secrets are wrapped in :class:`SecretStr` so they do not leak through
    ``__repr__`` or structured loggers. Access the plaintext via
    ``secret.get_secret_value()`` only at the point of use.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_",
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Reject unknown env vars with the PLATFORM_ prefix rather than
        # silently ignoring typos like PLATFORM_SCERET_KEY.
        extra="forbid",
    )

    # --- Runtime identity ---------------------------------------------------
    env: Literal["dev", "test", "prod"] = Field(
        default="dev",
        description="Deployment environment. Toggles strict checks (HSTS, cookie secure-flag, structured log level).",
    )
    app_name: str = Field(default="invoice-intelligence-platform", min_length=1, max_length=64)

    # --- Persistence -------------------------------------------------------
    # SQLAlchemy URL. SQLite for dev/test, Postgres for prod later. File
    # default lives OUTSIDE the package dir so pytest / deployment don't
    # accidentally bundle a db file into the wheel.
    database_url: str = Field(
        default=f"sqlite:///{(_HERE.parent / 'data' / 'business_layer.db').as_posix()}",
        min_length=1,
        description="SQLAlchemy database URL. Defaults to a SQLite file under <repo-root>/data/.",
    )

    # --- Secrets -----------------------------------------------------------
    # Master key for:
    #   - HMAC-signed session tokens (security.sessions)
    #   - AES-GCM column encryption of OAuth refresh tokens (security.encryption)
    #   - itsdangerous signed OAuth state tokens (CSRF on OAuth callback)
    #
    # Must be at least 32 bytes of entropy (256 bits). Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(32))"
    secret_key: SecretStr = Field(
        ...,
        description="Application master secret. Required; no default.",
    )

    # --- Session ----------------------------------------------------------
    session_cookie_name: str = Field(default="bl_session", min_length=1, max_length=64)
    session_ttl_seconds: int = Field(default=60 * 60 * 24 * 30, ge=60)  # 30 days
    session_cookie_secure: bool = Field(
        default=True,
        description="Set cookie Secure flag. Override to false only for local HTTP testing.",
    )
    session_cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax")

    # --- OTP --------------------------------------------------------------
    otp_ttl_seconds: int = Field(default=300, ge=30, le=900)  # 5 min
    otp_max_attempts: int = Field(default=5, ge=1, le=10)

    # --- Brute-force lockout ---------------------------------------------
    login_max_attempts: int = Field(default=10, ge=1, le=100)
    login_lockout_seconds: int = Field(default=900, ge=60)  # 15 min

    # --- Upload limits ----------------------------------------------------
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)  # 25 MB
    upload_max_pdf_pages: int = Field(default=50, ge=1, le=500)

    # --- Rate limits (per IP per route-group, per minute) -----------------
    rate_limit_login_per_min: int = Field(default=5, ge=1)
    rate_limit_otp_per_min: int = Field(default=5, ge=1)
    rate_limit_upload_per_min: int = Field(default=10, ge=1)

    # --- Security headers -------------------------------------------------
    # HSTS is skipped on dev (localhost HTTP). Enabled in prod only.
    hsts_enabled: bool = Field(default=False)

    # --- Logging ---------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # --- Gmail connector -------------------------------------------------
    # Path to the OAuth 2.0 Web Application client JSON downloaded from
    # Google Cloud Console → APIs & Services → Credentials.
    # Defaults to the `_dummy` placeholder so the server boots on a
    # fresh clone without crashing — Gmail features 404 until the
    # real file is swapped in and this path updated.
    google_oauth_client_file: Path = Field(
        default=_HERE.parent / "secrets" / "google_oauth_client_dummy.json",
        description="Path to google_oauth_client.json (rename from _dummy when real).",
    )

    # Public callback URL registered under Authorized redirect URIs in
    # the Google Cloud Console. Must match EXACTLY (scheme, host, port,
    # path — Google compares byte-for-byte).
    google_oauth_redirect_uri: str = Field(
        default="http://localhost:8001/api/oauth/google/callback",
    )

    # Poll cadence per connected source. Gmail quota is enormous; the
    # limiting factor is UX latency (user expects new invoices within
    # ~15 min of arrival). Tighten to 120s for demo if desired.
    gmail_poll_interval_seconds: int = Field(default=900, ge=60)

    # How far back to look on a first-time connection. Later ticks
    # only fetch messages newer than the source's last_polled_at.
    gmail_backfill_days: int = Field(default=30, ge=1, le=365)

    # --- Validators ------------------------------------------------------
    @field_validator("secret_key")
    @classmethod
    def _secret_min_length(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError(
                "PLATFORM_SECRET_KEY must be at least 32 characters "
                '(generate via `python -c "import secrets; print(secrets.token_urlsafe(32))"`)'
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    Cached so every caller sees the same instance. Tests override config
    by monkey-patching the environment and calling
    ``get_settings.cache_clear()``.
    """
    # pydantic-settings reads from env + .env.local on construction.
    return Settings()  # type: ignore[call-arg]
