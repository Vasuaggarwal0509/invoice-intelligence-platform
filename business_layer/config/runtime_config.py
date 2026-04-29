"""Operator-tunable runtime config loaded from ``config/config.json``.

Distinguished from :class:`business_layer.config.Settings` as follows:

* **Settings** — typed env vars (secrets, toggles, file paths). Deployed
  differently per environment (dev / CI / prod). Validated by
  pydantic-settings on import.
* **RuntimeConfig** — structured values an operator edits after deploy:
  keyword lists, filter tuning, rate-limit ceilings, allow-lists.
  Validated here on load.

Usage::

    from business_layer.config.runtime_config import get_runtime_config
    cfg = get_runtime_config()
    keywords = cfg.email_ingestion.subject_keywords

The accessor is LRU-cached like ``get_settings()``. Tests clear the
cache via ``get_runtime_config.cache_clear()`` after monkey-patching
the JSON path or the file contents.

No hot reload in v1 — a config edit requires a server restart. Easy
to layer on later with an ``inotify`` watcher or an explicit POST
endpoint; not needed today.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# Repo root = .../business_layer/config/runtime_config.py → parent × 3.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "config.json"


@dataclass(frozen=True)
class EmailIngestionConfig:
    """Subsection: filter + download knobs for email connectors.

    Consumed by :mod:`business_layer.services.connectors.gmail_connector`
    (and future Outlook / IMAP connectors).
    """

    subject_keywords: tuple[str, ...]
    supported_content_types: tuple[str, ...]
    backfill_days: int
    max_attachments_per_message: int
    max_messages_per_poll: int

    def has_keyword_filter(self) -> bool:
        """Return True if the caller should apply the keyword filter.

        Empty list = "match everything with an attachment" (useful for
        a broader audit mode). Callers branch on this so they don't
        emit ``subject:()`` to providers that reject empty groups.
        """
        return len(self.subject_keywords) > 0

    def normalised_keywords(self) -> tuple[str, ...]:
        """Lowercase + whitespace-stripped copy for substring matching."""
        return tuple(kw.strip().lower() for kw in self.subject_keywords if kw.strip())


@dataclass(frozen=True)
class RuntimeConfig:
    """Top-level runtime config bag.

    New sections (e.g. ``whatsapp_ingestion``, ``chat``) plug in by
    adding a dataclass and extending :func:`_load_from_dict`.
    """

    email_ingestion: EmailIngestionConfig


# ---------- loading ----------------------------------------------------


def _load_from_dict(doc: dict[str, Any]) -> RuntimeConfig:
    """Validate + construct a :class:`RuntimeConfig` from a parsed JSON dict.

    Raises:
        ValueError: On any shape / type mismatch. Raised early (at
            process start or after a config reload) so a malformed
            config never corrupts production behaviour.
    """
    # `_doc` keys are ignored — they're inline documentation for
    # operators editing the JSON. Don't treat them as data.
    email_raw = doc.get("email_ingestion")
    if not isinstance(email_raw, dict):
        raise ValueError("config.json: 'email_ingestion' section missing or not an object")

    def _str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"config.json: '{field_name}' must be a list of strings")
        return tuple(value)

    def _int_bounded(value: Any, field_name: str, *, lo: int, hi: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or not (lo <= value <= hi):
            raise ValueError(f"config.json: '{field_name}' must be an integer in [{lo}, {hi}]")
        return value

    email = EmailIngestionConfig(
        subject_keywords=_str_tuple(
            email_raw.get("subject_keywords", []), "email_ingestion.subject_keywords"
        ),
        supported_content_types=_str_tuple(
            email_raw.get("supported_content_types", []), "email_ingestion.supported_content_types"
        ),
        backfill_days=_int_bounded(
            email_raw.get("backfill_days", 30), "email_ingestion.backfill_days", lo=1, hi=365
        ),
        max_attachments_per_message=_int_bounded(
            email_raw.get("max_attachments_per_message", 10),
            "email_ingestion.max_attachments_per_message",
            lo=1,
            hi=100,
        ),
        max_messages_per_poll=_int_bounded(
            email_raw.get("max_messages_per_poll", 100),
            "email_ingestion.max_messages_per_poll",
            lo=1,
            hi=1000,
        ),
    )
    return RuntimeConfig(email_ingestion=email)


def _read_config_file(path: Path) -> dict[str, Any]:
    """Read + parse the config JSON file. Friendly errors on common mistakes."""
    if not path.exists():
        raise FileNotFoundError(
            f"Runtime config not found at {path}. "
            f"Copy config/config.json from the repo to this location."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"config.json at {path} is not valid JSON: {exc}") from exc


@lru_cache(maxsize=1)
def get_runtime_config() -> RuntimeConfig:
    """Return the process-wide :class:`RuntimeConfig`, loading on first call.

    Test helper: ``get_runtime_config.cache_clear()``.
    """
    return _load_from_dict(_read_config_file(_DEFAULT_CONFIG_PATH))


def load_from_path(path: Path) -> RuntimeConfig:
    """Load from an arbitrary path — used by tests that seed their own fixture."""
    return _load_from_dict(_read_config_file(path))
