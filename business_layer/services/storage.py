"""Blob storage — local filesystem, workspace-scoped.

Layout on disk::

    <repo-root>/data/blobs/{workspace_id}/{sha256[:2]}/{uuid}{ext}

``sha256[:2]`` is a shard prefix — prevents one directory ballooning
with tens of thousands of files. ``uuid`` is regenerated per upload so
a duplicate that dedups at the DB layer never has to choose between
two identical-hash filenames; storage and identity stay decoupled.

Rationale for **not** using python-magic (the OSS libmagic binding):
it needs ``libmagic`` installed out-of-band. On Windows this is
non-trivial and breaks new-developer setup. For our allowlist of
content types (PDF + a few image formats) magic-byte prefix checks
cover every case without extra deps.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Final

_log = logging.getLogger(__name__)

# Root for blob storage. Co-located with extraction_layer's dataset
# cache at repo root — same "generated-data at the top" convention.
_DEFAULT_BLOB_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent / "data" / "blobs"


# ---------- content-type sniffing --------------------------------------
#
# Mirrors the allowlist in extraction_layer.components.ocr.types.ContentType.
# If the set grows there, update here + add the signature below.

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGS = (b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb", b"\xff\xd8\xff\xee")
_PDF_SIG = b"%PDF-"
_TIFF_SIGS = (b"II*\x00", b"MM\x00*")
_WEBP_RIFF = b"RIFF"
_WEBP_MARK = b"WEBP"

# Extension per content-type — used for the stored filename. Keeps the
# blob readable on disk when an operator peeks at the dir.
_EXT_BY_TYPE: Final[dict[str, str]] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def sniff_content_type(data: bytes) -> str | None:
    """Return the content type by magic-byte prefix, or ``None`` if unknown.

    Only returns values in the allowlist backed by the extraction
    pipeline's :data:`ContentType` literal. Any other file type — zip,
    office, script — returns None so the upload handler can reject it.
    """
    if not data:
        return None
    if data.startswith(_PNG_SIG):
        return "image/png"
    if any(data.startswith(sig) for sig in _JPEG_SIGS):
        return "image/jpeg"
    if data.startswith(_PDF_SIG):
        return "application/pdf"
    if any(data.startswith(sig) for sig in _TIFF_SIGS):
        return "image/tiff"
    # WebP = "RIFF" + 4-byte size + "WEBP"
    if data.startswith(_WEBP_RIFF) and len(data) >= 12 and data[8:12] == _WEBP_MARK:
        return "image/webp"
    return None


# ---------- storage I/O ------------------------------------------------


def _blob_root() -> Path:
    """Return the storage root; created on first use.

    Indirection kept so tests can monkeypatch this without touching the
    module-level constant.
    """
    _DEFAULT_BLOB_ROOT.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_BLOB_ROOT


def compute_sha256(data: bytes) -> str:
    """Return the hex SHA-256 of ``data`` — used for dedup + integrity."""
    return hashlib.sha256(data).hexdigest()


def store_blob(
    *,
    workspace_id: str,
    data: bytes,
    content_type: str,
) -> tuple[str, str]:
    """Write ``data`` to disk and return ``(storage_key, sha256_hex)``.

    ``storage_key`` is a path RELATIVE to the blob root — that's what we
    persist in ``inbox_messages.file_storage_key``. Keeping it relative
    means a later move of the blob root (or a bulk backup/restore)
    doesn't require a DB migration.

    Raises:
        ValueError: If ``content_type`` is not in the storage allowlist.
    """
    if content_type not in _EXT_BY_TYPE:
        # Not a user-facing error — the upload handler filters earlier.
        # Here we defend against service-layer callers that forgot.
        raise ValueError(f"unsupported content_type: {content_type}")

    sha = compute_sha256(data)
    ext = _EXT_BY_TYPE[content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    rel_dir = Path(workspace_id) / sha[:2]
    rel_path = rel_dir / filename

    abs_dir = _blob_root() / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    abs_path = _blob_root() / rel_path
    # Write-then-rename would be safer under concurrent uploads, but a
    # fresh UUID per call means no-one else writes this exact path.
    abs_path.write_bytes(data)
    _log.info(
        "storage.blob_written",
        extra={"workspace_id": workspace_id, "bytes": len(data), "content_type": content_type},
    )
    return str(rel_path).replace("\\", "/"), sha


def read_blob(storage_key: str) -> bytes:
    """Return the bytes at ``storage_key``.

    Intentionally does not validate the path — storage_key is an
    internal value produced by :func:`store_blob`, never a user input.
    Routes serving images through this call must verify the invoice's
    ``workspace_id`` matches the caller's BEFORE they resolve the key.
    """
    path = _blob_root() / storage_key
    return path.read_bytes()


def blob_path(storage_key: str) -> Path:
    """Return the absolute path for ``storage_key`` (for FileResponse)."""
    return _blob_root() / storage_key
