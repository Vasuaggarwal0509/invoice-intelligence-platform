"""SQLite-backed persistence layer.

Engine, session context, and migrations. No business logic here — only
connection management and DDL. See :mod:`business_layer.repositories` for
query code.
"""

from .engine import get_engine, get_session, init_db, ping

__all__ = ["get_engine", "get_session", "init_db", "ping"]
