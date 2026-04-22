# data_sources

Dataset loaders that feed the pipeline. One implemented (Katanaml — the PoC
dataset), two scaffolded (MIDD for the Indian phase, SROIE for reference
benchmarking).

## Why the name is `data_sources/` and not `datasets/`

The monorepo layout in `project.md` §8.0 originally used `datasets/` for
this component. That directory name collides with the HuggingFace
`datasets` PyPI package, producing ambiguous import resolution
(`from datasets import load_dataset` inside our own `datasets/` can go
either way depending on `sys.path` order). Renamed to `data_sources/` —
same role, no shadowing. `project.md` updated to match.

## What this component does

A collection of dataset loaders behind a shared `BaseDataset` interface.
Every loader emits `Sample` objects with a uniform shape (image + raw
ground-truth dict), so downstream stages never branch on which dataset the
sample came from.

## Default dataset — `katanaml-org/invoices-donut-data-v1`

- 501 real invoices, pre-split 425 train / 50 validation / 26 test
- MIT licence
- Donut-style ground-truth JSON (`{"gt_parse": {"header": {...}, "items": [...]}}`)
- Loaded from the HuggingFace Hub, cached under `data/katanaml/` by default

Selection rationale in `research.md` §4.

## Install

The HuggingFace `datasets` library is listed in `requirements.txt`:

    # from the repo root, PowerShell
    uv pip install -r requirements.txt

On first dataset access, the HuggingFace hub is hit and files are cached.
Needs internet the first time only.

## Usage

    from data_sources import make_dataset
    from data_sources.katanaml_invoices import KatanamlInvoicesDataset

    ds = make_dataset("katanaml")
    print(f"Total: {len(ds)} samples across {ds.splits}")
    for split in ds.splits:
        print(f"  {split}: {ds.count(split)}")

    sample = ds.get("test", 0)
    sample.image          # numpy HxWx3 uint8 RGB
    sample.ground_truth   # parsed dict (see header_of / items_of helpers)

    # Typed accessors for the Donut wrapping
    header = KatanamlInvoicesDataset.header_of(sample)
    items  = KatanamlInvoicesDataset.items_of(sample)

## Feeding OCR from a sample

    from components.ocr import make_ocr
    from data_sources import make_dataset

    ocr = make_ocr("rapidocr")
    ds = make_dataset("katanaml")
    result = ocr.ocr(ds.get("test", 0).image)  # image is already an ndarray

## One-shot dataset download (CLI)

    python tools\download_dataset.py
    python tools\download_dataset.py --cache-dir C:\somewhere\else

## Datasets

| Key       | Status                    | Notes |
|-----------|---------------------------|-------|
| katanaml  | Implemented, default      | 501 invoices, MIT, Donut-style JSON |
| midd      | Scaffolded (post-PoC)     | 630 real Indian GST invoices, CC-BY 4.0, Zenodo DOI 10.5281/zenodo.5113009 |
| sroie    | Scaffolded (reference)    | 1000 ICDAR-2019 receipts, external calibration benchmark |

## Adding a new dataset

1. Create `data_sources/<name>/loader.py`.
2. Subclass `BaseDataset` from `data_sources.base`.
3. Implement:
   - `name` (short identifier — lands in `Sample.source_dataset`)
   - `splits` (list of split names)
   - `load(split)` (iterator over samples)
   - `get(split, index)` (random access)
   - `count(split)` (split size)
4. Register the dotted class path in `data_sources/factory.py`'s `_REGISTRY`.
5. Add tests in `data_sources/tests/`. Follow the pattern:
   - Unit tests for any parsing/normalisation helpers (no network).
   - End-to-end tests marked `dataset_heavy` (can be deselected).

## Running tests (PowerShell)

    # everything (will download dataset files on first run)
    pytest data_sources\tests

    # fast only — skip anything that hits HuggingFace Hub
    pytest -m "not dataset_heavy" data_sources\tests

    # and to skip both OCR model loads and dataset downloads
    pytest -m "not ocr_heavy and not dataset_heavy"

## Known edges

- `Sample.image` is strictly HxWx3 uint8 RGB. Loaders must convert
  PIL / RGBA / grayscale inputs at construction time.
- `Sample` is frozen (`ConfigDict(frozen=True)`). Mutating an existing
  sample raises; build a new one instead.
- `ground_truth` is a plain dict — the schema is dataset-specific. Typed
  accessors (e.g. `KatanamlInvoicesDataset.header_of`) live on the
  concrete loader class.
- First dataset access downloads files to `data/katanaml/`. Don't commit
  that directory (listed as `.gitignored` in `project.md` §8.0).
