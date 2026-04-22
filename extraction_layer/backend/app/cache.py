"""
JSONL-backed pipeline cache — populated lazily per invoice.

On first access of an invoice, the backend runs the full pipeline
(OCR -> extraction -> tables -> validation) and appends one JSONL line
with the result. Every subsequent access reads from the file.

Caching rules, per user direction (2026-04-19):

  * No warmup — the cache is **not** pre-populated on server start.
    Each invoice pays its OCR cost exactly once, when it's first
    clicked in the UI.
  * Persistent on disk as JSONL (one JSON record per line). Survives
    server restarts, greppable, no binary dependency.
  * The backend keeps an in-memory index for O(1) lookup, but the
    source of truth is the file.
"""

import json
import threading
from pathlib import Path
from typing import Any


class PipelineCache:
    """JSONL-backed lazy cache for pipeline outputs keyed by invoice ID."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._index: dict[str, dict[str, Any]] = {}
        self._loaded = False

    # ----- public API -----------------------------------------------------

    def get(self, invoice_id: str) -> dict[str, Any] | None:
        """Return the cached payload for `invoice_id`, or None if uncached."""
        self._ensure_loaded()
        with self._lock:
            return self._index.get(invoice_id)

    def put(self, invoice_id: str, payload: dict[str, Any]) -> None:
        """Add or overwrite an entry; appends a JSONL record to disk."""
        self._ensure_loaded()
        record = {"id": invoice_id, "data": payload}
        with self._lock:
            self._index[invoice_id] = payload
            # Single append — atomic-enough for one-process FastAPI;
            # if you ever scale to multiple workers, put this behind a
            # SQLite DB or a proper file-lock.
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def contains(self, invoice_id: str) -> bool:
        self._ensure_loaded()
        with self._lock:
            return invoice_id in self._index

    def keys(self) -> list[str]:
        self._ensure_loaded()
        with self._lock:
            return list(self._index.keys())

    # ----- internal -------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy first-read of the JSONL file into memory."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:  # another thread got here first
                return
            if self._path.exists():
                with self._path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            # Skip corrupt lines rather than refuse to boot.
                            continue
                        invoice_id = record.get("id")
                        data = record.get("data")
                        if invoice_id is None or data is None:
                            continue
                        # Later records overwrite earlier ones (same id).
                        self._index[invoice_id] = data
            self._loaded = True
