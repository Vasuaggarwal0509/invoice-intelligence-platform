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
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data") / "katanaml",
        help="Directory where HuggingFace caches the dataset (default: data/katanaml).",
    )
    args = parser.parse_args(argv)

    # Imports are deferred so `--help` works even without the library installed.
    from data_sources.katanaml_invoices import KatanamlInvoicesDataset

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
