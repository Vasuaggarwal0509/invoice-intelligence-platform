"""
Spot-check RapidOCR against Katanaml dataset invoices.

For N samples from a chosen split, this writes to a dated folder under
``evaluation/inspection/``:

  - ``NN_image.png``          — the invoice image (for eyeballing)
  - ``NN_ground_truth.json``  — Donut-parsed ground truth
  - ``NN_ocr.json``           — full RapidOCR output (tokens + lines + bboxes)
  - ``NN_comparison.md``      — human-readable side-by-side review sheet

Plus a top-level ``summary.md`` with a per-sample table + a Notes section
for you to record anything surprising as you review.

Usage (PowerShell, from repo root):

    python tools\\spotcheck_ocr.py
    python tools\\spotcheck_ocr.py --count 20 --split train
    python tools\\spotcheck_ocr.py --count 5 --start-index 10 --output-dir somewhere\\else
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from PIL import Image

from extraction_layer.components.ocr import make_ocr
from extraction_layer.data_sources import make_dataset
from extraction_layer.data_sources.katanaml_invoices import KatanamlInvoicesDataset


def _format_header_md(header: dict) -> str:
    if not header:
        return "(no header fields)\n"
    rows = ["| Field | Value |", "|---|---|"]
    for k, v in header.items():
        if isinstance(v, dict):
            v_str = " / ".join(f"{ik}={iv}" for ik, iv in v.items())
        elif isinstance(v, list):
            v_str = " / ".join(str(x) for x in v)
        else:
            v_str = str(v)
        v_str = _md_safe(v_str)
        rows.append(f"| {k} | {v_str} |")
    return "\n".join(rows) + "\n"


def _format_items_md(items: list) -> str:
    if not items:
        return "(no line items)\n"
    out = []
    for i, item in enumerate(items, 1):
        if isinstance(item, dict):
            fields = ", ".join(f"**{k}**={_md_safe(str(v))}" for k, v in item.items())
            out.append(f"{i}. {fields}")
        else:
            out.append(f"{i}. {_md_safe(str(item))}")
    return "\n".join(out) + "\n"


def _format_ocr_lines_md(lines: list[dict]) -> str:
    if not lines:
        return "(no lines detected)\n"
    rows = ["| # | Confidence | Text |", "|---|---|---|"]
    for i, line in enumerate(lines, 1):
        conf = f"{line['confidence']:.2f}"
        text = _md_safe(line["text"])
        rows.append(f"| {i} | {conf} | {text} |")
    return "\n".join(rows) + "\n"


def _md_safe(text: str) -> str:
    """Minimal escaping so markdown tables don't break on pipe / newline."""
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export N Katanaml invoices + ground truth + RapidOCR output for visual inspection."
    )
    parser.add_argument("--count", type=int, default=10, help="Number of samples to inspect (default: 10).")
    parser.add_argument("--split", default="test", help="Dataset split (default: test).")
    parser.add_argument("--start-index", type=int, default=0, help="First sample index in the split (default: 0).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Where to write the inspection bundle. "
            "Default: evaluation/inspection/YYYY-MM-DD_katanaml_spotcheck/"
        ),
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="HuggingFace cache_dir passed to the dataset loader (optional).",
    )
    args = parser.parse_args(argv)

    today = date.today().isoformat()
    if args.output_dir is None:
        args.output_dir = Path("evaluation") / "inspection" / f"{today}_katanaml_spotcheck"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading dataset ...")
    if args.cache_dir is not None:
        ds = KatanamlInvoicesDataset(cache_dir=args.cache_dir)
    else:
        ds = make_dataset("katanaml")

    if args.split not in ds.splits:
        print(f"ERROR: split {args.split!r} not available. Got splits: {ds.splits}")
        return 2

    total = ds.count(args.split)
    if args.start_index >= total:
        print(f"ERROR: --start-index {args.start_index} >= split size {total}")
        return 2
    end = min(args.start_index + args.count, total)

    print("Loading OCR (RapidOCR / PP-OCRv5) ...")
    ocr = make_ocr("rapidocr")
    ocr.warmup()

    n_samples = end - args.start_index
    print(f"Exporting {n_samples} samples from split {args.split!r} -> {args.output_dir.resolve()}")

    summary_rows = []
    for i in range(args.start_index, end):
        n = i - args.start_index
        prefix = f"{n:02d}"
        sample = ds.get(args.split, i)

        # Image
        img_path = args.output_dir / f"{prefix}_image.png"
        Image.fromarray(sample.image).save(img_path)
        h, w = sample.image.shape[:2]

        # Ground truth
        gt_path = args.output_dir / f"{prefix}_ground_truth.json"
        gt_path.write_text(
            json.dumps(sample.ground_truth, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # OCR
        ocr_result = ocr.ocr(sample.image)
        ocr_path = args.output_dir / f"{prefix}_ocr.json"
        ocr_path.write_text(ocr_result.model_dump_json(indent=2), encoding="utf-8")

        # Comparison markdown
        header = KatanamlInvoicesDataset.header_of(sample)
        items = KatanamlInvoicesDataset.items_of(sample)
        lines_dumped = [line.model_dump(mode="json") for line in ocr_result.lines]
        comparison_md = "\n".join([
            f"# Spot check — sample {n:02d} ({sample.id})",
            "",
            f"- **Split**: `{sample.split}`",
            f"- **Dataset row**: {sample.metadata.get('row_index', '?')}",
            f"- **Image**: `{img_path.name}` ({w}x{h})",
            f"- **OCR duration**: {ocr_result.duration_ms:.1f} ms",
            f"- **Lines detected**: {len(ocr_result.lines)}",
            f"- **Tokens derived**: {len(ocr_result.tokens)}",
            "",
            "## Ground truth",
            "",
            "### Header",
            "",
            _format_header_md(header),
            "### Line items",
            "",
            _format_items_md(items),
            "## RapidOCR output",
            "",
            _format_ocr_lines_md(lines_dumped),
        ])
        (args.output_dir / f"{prefix}_comparison.md").write_text(comparison_md, encoding="utf-8")

        summary_rows.append(
            {
                "n": n,
                "id": sample.id,
                "dims": f"{w}x{h}",
                "lines": len(ocr_result.lines),
                "tokens": len(ocr_result.tokens),
                "ocr_ms": ocr_result.duration_ms,
                "gt_fields": len(header),
                "gt_items": len(items),
            }
        )
        print(
            f"  [{n:02d}] {sample.id}: {len(ocr_result.lines)} lines, "
            f"{ocr_result.duration_ms:.0f} ms, "
            f"gt-fields={len(header)}, gt-items={len(items)}"
        )

    # Summary
    summary_lines = [
        f"# Spot check summary — {today}",
        "",
        f"- **Dataset**: `{ds.name}`",
        f"- **Split**: `{args.split}`",
        f"- **Samples inspected**: {n_samples} (indices {args.start_index}-{end - 1})",
        f"- **OCR backend**: `rapidocr` (PP-OCRv5 via ONNX Runtime)",
        "",
        "## Per-sample",
        "",
        "| # | ID | Image (WxH) | Lines | Tokens | OCR ms | GT header fields | GT items |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in summary_rows:
        summary_lines.append(
            f"| {r['n']:02d} | `{r['id']}` | {r['dims']} | "
            f"{r['lines']} | {r['tokens']} | {r['ocr_ms']:.0f} | "
            f"{r['gt_fields']} | {r['gt_items']} |"
        )

    # Aggregate stats
    if summary_rows:
        avg_lines = sum(r["lines"] for r in summary_rows) / len(summary_rows)
        avg_ms = sum(r["ocr_ms"] for r in summary_rows) / len(summary_rows)
        total_ms = sum(r["ocr_ms"] for r in summary_rows)
        summary_lines += [
            "",
            "## Aggregate",
            "",
            f"- Average lines/invoice: **{avg_lines:.1f}**",
            f"- Average OCR latency: **{avg_ms:.0f} ms**",
            f"- Total OCR time (wall clock, serial): **{total_ms:.0f} ms**",
        ]

    summary_lines += [
        "",
        "## How to review",
        "",
        "1. Open each `NN_image.png` in an image viewer and eyeball it.",
        "2. Open `NN_comparison.md` next to the image — read the ground-truth header + items, then skim the RapidOCR output table.",
        "3. Flag anything surprising in the Notes section below:",
        "   - missed critical fields (invoice number, date, total),",
        "   - wrong digit recognition on numeric fields,",
        "   - low confidence on important values,",
        "   - layout quirks that the pipeline will need to handle.",
        "",
        "## Notes (fill in after review)",
        "",
        "- ",
    ]

    summary_path = args.output_dir / "summary.md"
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    print(f"\nSummary: {summary_path}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
