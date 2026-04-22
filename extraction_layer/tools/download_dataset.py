"""
CLI — download and cache the Katanaml Invoices dataset.

Usage (PowerShell):
    python tools\\download_dataset.py
    python tools\\download_dataset.py --cache-dir data\\katanaml

On first run this downloads the dataset from HuggingFace Hub; subsequent
runs re-use the cache.
"""

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the Katanaml Invoices dataset (HuggingFace Hub)."
    )
    # Default cache dir anchored at <repo_root>/data/katanaml/ regardless of CWD.
    # __file__ = extraction_layer/tools/download_dataset.py → up 3 = repo root.
    # (Kept at repo root, not under extraction_layer/, so HF's path-mangled lock
    # filenames stay under Windows MAX_PATH=260.)
    _default_cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "katanaml"
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_default_cache_dir,
        help=f"Directory where HuggingFace caches the dataset (default: {_default_cache_dir}).",
    )
    args = parser.parse_args(argv)

    # Imports are deferred so `--help` works even without the library installed.
    from extraction_layer.data_sources.katanaml_invoices import KatanamlInvoicesDataset

    print(f"Cache dir: {args.cache_dir.resolve()}")
    ds = KatanamlInvoicesDataset(cache_dir=args.cache_dir)
    print(f"Dataset : {ds.name}")
    print(f"Splits  : {ds.splits}")
    for split in ds.splits:
        print(f"   {split:<12} {ds.count(split)} samples")
    print(f"Total   : {len(ds)} samples")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
