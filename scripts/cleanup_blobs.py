"""Delete blob files on disk that no DB row references.

Walks ``data/blobs/`` and removes any file whose relative path is NOT
present in ``inbox_messages.file_storage_key``. Empty workspace dirs
are pruned afterwards.

Safe by construction:

  * Anything the app might serve (every row in ``inbox_messages``) is
    skipped — those are the live blobs the image route resolves.
  * If a row exists but the file is missing, we report it. We never
    re-create or download.

Run with::

    venv/bin/python -m scripts.cleanup_blobs
    # or:
    venv/bin/python -m scripts.cleanup_blobs --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from business_layer.db import engine as db_engine
from business_layer.db.tables import inbox_messages as t_inbox

BLOB_ROOT = Path("data/blobs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only; don't delete")
    args = ap.parse_args()

    if not BLOB_ROOT.is_dir():
        print(f"no blob root at {BLOB_ROOT} — nothing to clean")
        return 0

    db_engine.init_db()
    with db_engine.get_session() as session:
        referenced = {
            row.file_storage_key
            for row in session.execute(select(t_inbox.c.file_storage_key)).all()
        }

    on_disk = {
        str(p.relative_to(BLOB_ROOT)).replace("\\", "/")
        for p in BLOB_ROOT.rglob("*")
        if p.is_file()
    }
    orphaned = sorted(on_disk - referenced)
    missing = sorted(referenced - on_disk)

    print(f"blobs on disk:           {len(on_disk)}")
    print(f"referenced by DB:        {len(referenced)}")
    print(f"orphaned (will delete):  {len(orphaned)}")
    print(f"missing from disk:       {len(missing)}")

    if missing:
        print()
        print("WARNING — these blobs are referenced by the DB but missing on disk:")
        for k in missing[:10]:
            print(f"  {k}")
        if len(missing) > 10:
            print(f"  ... + {len(missing) - 10} more")

    if not orphaned:
        print()
        print("Nothing to delete.")
        return 0

    if args.dry_run:
        print()
        print(f"--dry-run: not deleting {len(orphaned)} files")
        return 0

    deleted = 0
    bytes_freed = 0
    for key in orphaned:
        p = BLOB_ROOT / key
        try:
            bytes_freed += p.stat().st_size
            p.unlink()
            deleted += 1
        except FileNotFoundError:
            pass  # someone else removed it

    # Prune empty shard + workspace dirs left behind after the file deletions.
    pruned_dirs = 0
    for d in sorted(BLOB_ROOT.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
                pruned_dirs += 1
            except OSError:
                pass

    print()
    print(f"deleted {deleted} files, freed {bytes_freed / 1024:.1f} KB")
    print(f"pruned {pruned_dirs} empty directories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
