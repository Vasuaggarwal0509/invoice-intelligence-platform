"""Domain exception hierarchy.

Raise these from service-layer code. The FastAPI handler in
:mod:`business_layer.errors.handlers` maps each class to an HTTP status
code and a stable JSON body shape.

Design rules:

* One abstract root (:class:`PlatformError`), two abstract branches
  (:class:`ClientError`, :class:`ServerError`).
* Concrete classes set ``status_code`` and ``error_code`` at class level,
  not at instantiation — lets the handler render a response without
  reading the instance dict.
* Every exception carries an optional ``detail`` string (safe to show
  users) and ``context`` dict (never shown; logged server-side). The
  distinction is what lets us say "wrong password" to the user while
  logging ``{"user_id": "...", "attempt_n": 7}`` for SRE triage.
* Never include PII (GSTIN, tokens, email contents) in ``detail``.
  Reviewable by convention; enforced by the PII-redaction log
  processor for anything that does slip through.
"""

from __future__ import annotations

from typing import Any


class PlatformError(Exception):
    """Abstract root of every exception we raise on purpose.

    Don't raise this directly — use one of the concrete subclasses.
    Using an abstract root lets the FastAPI handler catch *everything
    intentional* with a single ``except PlatformError:`` branch, leaving
    the ``except Exception:`` branch strictly for unexpected crashes.
    """

    status_code: int = 500
    error_code: str = "platform_error"

    def __init__(
        self,
        detail: str = "",
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail or self.error_code)
        self.detail: str = detail
        self.context: dict[str, Any] = context or {}


# ---------- 4xx — client-caused -----------------------------------------


class ClientError(PlatformError):
    """4xx branch root. Something the caller did is wrong."""

    status_code = 400
    error_code = "client_error"


class AuthenticationError(ClientError):
    """401 — credentials missing or invalid.

    Kept deliberately vague by default (``"invalid credentials"``) so
    replies don't tell an attacker whether the username or password was
    wrong. Log context server-side for triage.
    """

    status_code = 401
    error_code = "authentication_failed"


class AuthorizationError(ClientError):
    """403 — caller identified but not permitted.

    Prefer :class:`NotFoundError` for cross-tenant access attempts — a
    404 leaks strictly less than a 403 ("resource exists but you can't
    see it").
    """

    status_code = 403
    error_code = "forbidden"


class NotFoundError(ClientError):
    """404 — target does not exist OR caller has no business knowing it exists."""

    status_code = 404
    error_code = "not_found"


class ConflictError(ClientError):
    """409 — unique-constraint collision, duplicate upload, etc."""

    status_code = 409
    error_code = "conflict"


class ValidationError(ClientError):
    """422 — request body fails domain-level invariants.

    Schema-level failures (Pydantic's own ValidationError) produce 422
    automatically via FastAPI. This class is for *business* validation
    that runs after the schema parse succeeds — e.g. "GSTIN checksum
    invalid".
    """

    status_code = 422
    error_code = "validation_failed"


class BusinessRuleError(ClientError):
    """400 — a domain rule was violated.

    Use when no other 4xx fits. Example: trying to approve an invoice
    that is already approved.
    """

    status_code = 400
    error_code = "business_rule_violated"


class RateLimitedError(ClientError):
    """429 — too many requests. Carries a ``retry_after_seconds`` hint."""

    status_code = 429
    error_code = "rate_limited"

    def __init__(
        self,
        detail: str = "",
        *,
        retry_after_seconds: int,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail, context=context)
        self.retry_after_seconds = retry_after_seconds


# ---------- 5xx — server-caused ----------------------------------------


class ServerError(PlatformError):
    """5xx branch root. Something on our side failed.

    Responses NEVER carry server-side detail. The handler replaces any
    :attr:`detail` with a generic string before emitting the response.
    Original detail + context are logged, stamped with ``request_id``,
    so on-call can grep.
    """

    status_code = 500
    error_code = "server_error"


class DependencyError(ServerError):
    """502 — an external dependency we rely on is not behaving.

    OCR backend crashed, OAuth provider 5xx'd, etc.
    """

    status_code = 502
    error_code = "dependency_error"


class StorageError(ServerError):
    """503 — database unreachable, disk full, blob storage unwritable."""

    status_code = 503
    error_code = "storage_unavailable"


class InternalError(ServerError):
    """500 — the catch-all for code-level bugs.

    Prefer a more specific subclass where one exists; use this when the
    failure is genuinely "we have a bug".
    """

    status_code = 500
    error_code = "internal_error"
