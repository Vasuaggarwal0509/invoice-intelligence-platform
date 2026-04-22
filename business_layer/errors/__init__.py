"""Domain exception hierarchy + FastAPI exception handlers.

One root (:class:`PlatformError`), two branches:

- :class:`ClientError` → 4xx responses (validation, auth, not-found, conflict).
- :class:`ServerError` → 5xx responses (dependency/storage/internal).

Raise from service-layer code. The global handler registered by
:func:`business_layer.app.app_factory` maps these to JSON responses with a
stable shape + a ``request_id`` the user can quote.
"""

from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    ClientError,
    ConflictError,
    DependencyError,
    InternalError,
    NotFoundError,
    PlatformError,
    RateLimitedError,
    ServerError,
    StorageError,
    ValidationError,
)
from .handlers import register_exception_handlers

__all__ = [
    "PlatformError",
    "ClientError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "BusinessRuleError",
    "RateLimitedError",
    "ServerError",
    "DependencyError",
    "StorageError",
    "InternalError",
    "register_exception_handlers",
]
