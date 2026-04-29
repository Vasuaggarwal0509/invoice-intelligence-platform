"""SQLAlchemy engine + session management + migration runner.

Single engine per process, built lazily from :class:`Settings`. SQLite
pragmas are set on every new connection — SQLite DOES NOT remember
``foreign_keys=ON`` across connections, it's per-connection. Miss that
once and ``ON DELETE CASCADE`` silently becomes a no-op.

Migrations are plain ``.sql`` files in ``migrations/`` executed in
sorted order. No Alembic for Sprint 0 — the schema is small and we
need zero abstraction to run a file full of ``CREATE TABLE IF NOT
EXISTS``. When the schema starts evolving across real tenant data,
swap in Alembic behind :func:`init_db`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from business_layer.config import Settings, get_settings

_log = logging.getLogger(__name__)

# Lazy singletons. Production reads them once; tests override by
# calling :func:`_reset_for_tests`.
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


# ---------- engine construction ----------------------------------------


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """Attach a listener that sets pragmas on every new SQLite connection.

    Called only for SQLite URLs; Postgres doesn't need this.
    """

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        # Enforce foreign keys. OFF by default in SQLite — silent data loss.
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL gives concurrent readers; write serialises but doesn't block reads.
        cursor.execute("PRAGMA journal_mode=WAL")
        # Reasonable safety / throughput trade-off for app-level DBs.
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def _build_engine(settings: Settings) -> Engine:
    """Construct the SQLAlchemy engine from settings.

    SQLite URLs: ensure the target directory exists (pysqlite won't
    create it) and attach PRAGMA listener.

    Postgres URLs: no extra config; future work.
    """
    url = settings.database_url

    if url.startswith("sqlite:///"):
        db_path_str = url[len("sqlite:///") :]
        is_memory = db_path_str == ":memory:" or url == "sqlite://"
        if db_path_str and not is_memory:
            db_path = Path(db_path_str)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        # `check_same_thread=False` lets the session be used from the
        # worker thread (Sprint 2 uses an in-process thread). Safe
        # because we gate writes behind transactions + our own locks.
        #
        # For in-memory DBs (tests), StaticPool is mandatory — without
        # it each new connection opens a FRESH empty database. Docs
        # reference: "Using a Memory Database in Multiple Threads" in
        # the SQLAlchemy SQLite dialect guide.
        engine_kwargs: dict[str, object] = {
            "future": True,
            "connect_args": {"check_same_thread": False},
        }
        if is_memory:
            engine_kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **engine_kwargs)  # type: ignore[arg-type]
        _apply_sqlite_pragmas(engine)
        return engine

    # Postgres or future dialects — no connect_args customisation yet.
    return create_engine(url, future=True, pool_pre_ping=True)


def get_engine() -> Engine:
    """Return the process-wide engine, constructing it on first call."""
    global _engine, _SessionFactory
    if _engine is None:
        _engine = _build_engine(get_settings())
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


# ---------- session context --------------------------------------------


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a SQLAlchemy session inside an auto-committed transaction.

    Usage::

        with get_session() as session:
            session.execute(...)
            # implicit commit on successful exit; rollback on exception

    Routes should depend on this via a FastAPI ``Depends()`` wrapper
    rather than calling it directly — keeps the layer boundary clean
    (routes → services → repos → this).
    """
    get_engine()  # build on demand
    assert _SessionFactory is not None  # for type-checkers
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------- migrations -------------------------------------------------


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


_MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  INTEGER NOT NULL
)
"""


def init_db() -> None:
    """Apply each ``.sql`` file in ``migrations/`` in sorted order, once.

    A tracking table (``schema_migrations``) records which files have
    already been applied, keyed by filename. On reboot we skip files
    whose name appears in the table.

    The first migration (0001_init.sql) uses ``CREATE TABLE IF NOT
    EXISTS`` exclusively, so a cold-start (fresh DB → 0001 → tracking
    table) and a warm-start (existing DB pre-tracking → 0001 re-runs
    as no-op → tracking table catches up → 0002 applies once) are
    both safe.

    Non-idempotent statements (``ALTER TABLE ... ADD COLUMN``) are
    fine from 0002 onwards because the tracker prevents re-run.
    """
    engine = get_engine()
    migrations = sorted(_migrations_dir().glob("*.sql"))
    if not migrations:
        _log.warning(
            "db.init.no_migrations_found", extra={"migrations_dir": str(_migrations_dir())}
        )
        return

    with engine.begin() as conn:
        dbapi_conn = conn.connection
        cursor = dbapi_conn.cursor()

        # Always ensure the tracker exists first.
        cursor.execute(_MIGRATIONS_TABLE_DDL)
        cursor.execute("SELECT filename FROM schema_migrations")
        applied: set[str] = {row[0] for row in cursor.fetchall()}

        import time as _time

        for path in migrations:
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            # executescript runs multiple statements; wraps its own commit.
            cursor.executescript(sql)
            cursor.execute(
                "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?)",
                (path.name, int(_time.time() * 1000)),
            )
            _log.info("db.migration.applied", extra={"migration": path.name})

        cursor.close()


def _reset_for_tests() -> None:
    """Test-only helper: discard the cached engine + session factory.

    Call from a pytest fixture after monkey-patching the ``PLATFORM_``
    env vars, so the next ``get_engine()`` rebuilds against the test DB
    URL. Production code must never call this.
    """
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


# ---------- health check -----------------------------------------------


def ping() -> bool:
    """Return True if the DB is reachable — used by /health.

    Runs a trivial ``SELECT 1`` inside a fresh session. Any exception
    → False (callers translate to a 503/StorageError).
    """
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:  # pragma: no cover - exercised in integration tests
        _log.exception("db.ping.failed")
        return False
