"""Explicit SQLAlchemy Core :class:`Table` objects for every business_layer table.

Rationale: we use SQLAlchemy Core (not ORM) for repositories so query
shape stays obvious — ``select(t.users).where(...)`` is the same as the
SQL it emits. Declaring Tables here (rather than reflecting from
``schema.sql`` at runtime) gives three wins:

* **Static analysis** — type-checkers see column types.
* **IDE autocomplete** — every query references a known column name.
* **No startup reflection roundtrip** — tests run against :memory:
  without waiting for a reflect call.

The canonical DDL is ``schema.sql``. This module describes the *same*
schema in SQLAlchemy terms. Keep them in sync; Sprint 0's hash-based
test would catch a drift where a column in ``schema.sql`` wasn't listed
here (the failing insert would surface it immediately).

No Primary/Foreign Key constraints beyond what SQLAlchemy needs to
build SELECTs — referential integrity is enforced by the DB itself
(``PRAGMA foreign_keys=ON`` set in :mod:`business_layer.db.engine`).
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

# Single MetaData for all business_layer tables. Keeps them addressable
# for reflection-based tooling if we ever need it (e.g. generating an
# ER diagram).
metadata = MetaData()


# ---------- Identity + tenancy ------------------------------------------

users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("role", String, nullable=False),
    Column("email", String, unique=True),
    Column("phone", String, unique=True),
    Column("password_hash", String),
    Column("display_name", String, nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("last_login_at", BigInteger),
    Column("locked_until", BigInteger),
    Column("failed_login_count", Integer, nullable=False, server_default="0"),
    CheckConstraint("role IN ('business','ca','admin')", name="ck_users_role"),
    CheckConstraint(
        "(email IS NOT NULL) OR (phone IS NOT NULL)",
        name="ck_users_has_contact",
    ),
)

workspaces = Table(
    "workspaces",
    metadata,
    Column("id", String, primary_key=True),
    Column("owner_user_id", String, nullable=False),
    Column("name", String, nullable=False),
    Column("gstin", String),
    Column("created_via", String, nullable=False),
    Column("tier", String, nullable=False, server_default="'free'"),
    Column("status", String, nullable=False, server_default="'active'"),
    Column("region", String),
    Column("default_extraction_mode", String, nullable=False, server_default="'instant'"),
    Column("ca_gstin", String),
    Column("created_at", BigInteger, nullable=False),
    Index("ix_workspaces_ca_gstin", "ca_gstin"),
    UniqueConstraint("owner_user_id", name="uq_workspaces_owner"),
    CheckConstraint(
        "created_via IN ('self_signup','invite','admin')",
        name="ck_workspaces_created_via",
    ),
    CheckConstraint(
        "default_extraction_mode IN ('instant','scheduled','manual')",
        name="ck_workspaces_extraction_mode",
    ),
)


# ---------- Ingestion ---------------------------------------------------

sources = Table(
    "sources",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("kind", String, nullable=False),
    Column("label", String),
    Column("status", String, nullable=False),
    Column("default_extraction_mode", String, nullable=False),
    Column("credentials_encrypted", LargeBinary),
    Column("last_polled_at", BigInteger),
    Column("created_at", BigInteger, nullable=False),
    Index("ix_sources_workspace", "workspace_id"),
)

inbox_messages = Table(
    "inbox_messages",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("source_id", String),
    Column("external_id", String),
    Column("sender", String),
    Column("subject", String),
    Column("received_at", BigInteger, nullable=False),
    Column("content_type", String, nullable=False),
    Column("file_storage_key", String, nullable=False),
    Column("file_size_bytes", BigInteger, nullable=False),
    Column("file_sha256", String, nullable=False),
    Column("status", String, nullable=False),
    Column("ignored_reason", String),
    Column("created_at", BigInteger, nullable=False),
    UniqueConstraint("workspace_id", "file_sha256", name="uq_inbox_dedup"),
)


# ---------- Extraction outputs ------------------------------------------

invoices = Table(
    "invoices",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("inbox_message_id", String, nullable=False),
    Column("vendor_name", String),
    Column("client_name", String),
    Column("client_gstin", String),
    Column("seller_gstin", String),
    Column("invoice_no", String),
    Column("invoice_date", String),
    Column("total_amount_minor", BigInteger),
    Column("currency", String, nullable=False, server_default="'INR'"),
    Column("status", String, nullable=False, server_default="'pending'"),
    Column("created_at", BigInteger, nullable=False),
    Column("approved_at", BigInteger),
    Column("approved_by_user_id", String),
)

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("invoice_id", String, nullable=False),
    Column("pipeline_version", String, nullable=False),
    Column("ocr_result_json", String, nullable=False),
    Column("extraction_result_json", String, nullable=False),
    Column("tables_result_json", String, nullable=False),
    Column("validation_result_json", String),
    Column("ocr_ms", Numeric),
    Column("extract_ms", Numeric),
    Column("tables_ms", Numeric),
    Column("validate_ms", Numeric),
    Column("total_ms", Numeric),
    Column("created_at", BigInteger, nullable=False),
    UniqueConstraint("invoice_id", "pipeline_version", name="uq_pipeline_runs"),
)

validation_findings = Table(
    "validation_findings",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("invoice_id", String, nullable=False),
    Column("rule_name", String, nullable=False),
    Column("target", String),
    Column("outcome", String, nullable=False),
    Column("reason", String),
    Column("expected", String),
    Column("observed", String),
    Column("created_at", BigInteger, nullable=False),
)


# ---------- Job queue ---------------------------------------------------

jobs = Table(
    "jobs",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("inbox_message_id", String, nullable=False),
    Column("invoice_id", String),
    Column("stage", String, nullable=False),
    Column("state", String, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("max_attempts", Integer, nullable=False, server_default="3"),
    Column("next_run_at", BigInteger, nullable=False),
    Column("started_at", BigInteger),
    Column("finished_at", BigInteger),
    Column("error_message", String),
    Column("created_at", BigInteger, nullable=False),
)


# ---------- Audit + sessions + OTP + CA overrides -----------------------

events = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String),
    Column("actor_user_id", String),
    Column("action", String, nullable=False),
    Column("target_type", String),
    Column("target_id", String),
    Column("metadata_json", String),
    Column("ts", BigInteger, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("user_id", String, nullable=False),
    Column("token_hash", String, nullable=False, unique=True),
    Column("expires_at", BigInteger, nullable=False),
    Column("user_agent", String),
    Column("ip_address", String),
    Column("revoked_at", BigInteger),
    Column("created_at", BigInteger, nullable=False),
)

otp_challenges = Table(
    "otp_challenges",
    metadata,
    Column("id", String, primary_key=True),
    Column("phone", String, nullable=False),
    Column("code_hash", String, nullable=False),
    Column("purpose", String, nullable=False),
    Column("expires_at", BigInteger, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("max_attempts", Integer, nullable=False, server_default="5"),
    Column("used_at", BigInteger),
    Column("created_at", BigInteger, nullable=False),
)

client_label_overrides = Table(
    "client_label_overrides",
    metadata,
    Column("workspace_id", String, primary_key=True),
    Column("client_gstin", String, primary_key=True),
    Column("display_name", String, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)
