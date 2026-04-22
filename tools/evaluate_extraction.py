"""
Evaluate G1+G2 heuristic extraction on katanaml.

For each sample in the chosen split, runs OCR -> extraction, compares each
extracted field against the Donut ground truth, and computes per-field
exact-match F1 plus an overall average. Writes the report to
`evaluation/reports/YYYY-MM-DD_G1G2.md` (and a sibling `.json` for
programmatic inspection).

Usage (PowerShell):

    python tools\\evaluate_extraction.py
    python tools\\evaluate_extraction.py --split validation
    python tools\\evaluate_extraction.py --gate 0.85 --max-samples 5

Exit code is 0 if the gate passes, 1 if it fails.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from components.extraction import make_extractor
from components.ocr import make_ocr
from data_sources import make_dataset
from data_sources.katanaml_invoices import KatanamlInvoicesDataset


FIELDS: list[str] = [
    "invoice_no",
    "invoice_date",
    "seller",
    "client",
    "seller_tax_id",
    "client_tax_id",
    "iban",
]


def _normalize(s: Any) -> str | None:
    if s is None:
        return None
    return str(s).strip() or None


def _extract_gt_field(sample, field_name: str) -> str | None:
    header = KatanamlInvoicesDataset.header_of(sample)
    value = header.get(field_name)
    return _normalize(value)


def _evaluate(predicted: str | None, gt: str | None) -> str:
    """Return one of: 'correct', 'wrong', 'missed', 'spurious', 'both_none'."""
    p = _normalize(predicted)
    g = _normalize(gt)
    if g is None and p is None:
        return "both_none"
    if g is not None and p is None:
        return "missed"
    if g is None and p is not None:
        return "spurious"
    if p == g:
        return "correct"
    return "wrong"


def _f1(stats: dict[str, int]) -> tuple[float, float, float]:
    """From per-outcome counts, compute (precision, recall, F1)."""
    tp = stats["correct"]
    fp = stats["wrong"] + stats["spurious"]
    fn = stats["missed"] + stats["wrong"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return precision, recall, 0.0
    return precision, recall, 2 * precision * recall / (precision + recall)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate G1+G2 heuristic extractor on a katanaml split."
    )
    parser.add_argument("--split", default="test", help="Dataset split (default: test).")
    parser.add_argument(
        "--gate",
        type=float,
        default=0.90,
        help="Average per-field F1 threshold. Exit 0 if met, 1 otherwise.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Limit the number of samples (for smoke runs).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation") / "reports",
        help="Where the markdown + JSON report land.",
    )
    args = parser.parse_args(argv)

    today = date.today().isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_md = args.output_dir / f"{today}_G1G2.md"
    report_json = args.output_dir / f"{today}_G1G2.json"

    print("Loading dataset ...")
    ds = make_dataset("katanaml")
    if args.split not in ds.splits:
        print(f"ERROR: split {args.split!r} not available. Got splits: {ds.splits}")
        return 2

    total = ds.count(args.split)
    if args.max_samples is not None:
        total = min(total, args.max_samples)

    print("Loading OCR (RapidOCR / PP-OCRv5) ...")
    ocr = make_ocr("rapidocr")
    ocr.warmup()

    print("Loading extractor (heuristic) ...")
    extractor = make_extractor("heuristic")

    per_field_stats: dict[str, dict[str, int]] = {
        f: {"correct": 0, "wrong": 0, "missed": 0, "spurious": 0, "both_none": 0}
        for f in FIELDS
    }
    sample_records: list[dict[str, Any]] = []

    start_all = time.perf_counter()
    for i in range(total):
        sample = ds.get(args.split, i)
        ocr_result = ocr.ocr(sample.image)
        extraction = extractor.extract(ocr_result)

        record: dict[str, Any] = {
            "id": sample.id,
            "fields": {},
            "ocr_ms": ocr_result.duration_ms,
            "extract_ms": extraction.duration_ms,
        }
        for field in FIELDS:
            predicted = extraction.get_value(field)
            gt = _extract_gt_field(sample, field)
            outcome = _evaluate(predicted, gt)
            per_field_stats[field][outcome] += 1
            record["fields"][field] = {
                "predicted": predicted,
                "ground_truth": gt,
                "outcome": outcome,
            }
        sample_records.append(record)
        correct_n = sum(
            1 for f in FIELDS if record["fields"][f]["outcome"] == "correct"
        )
        print(
            f"  [{i:02d}] {sample.id}: "
            f"correct {correct_n}/{len(FIELDS)}  "
            f"ocr {ocr_result.duration_ms:.0f}ms  extract {extraction.duration_ms:.1f}ms"
        )

    total_wall_s = time.perf_counter() - start_all
    per_field_f1 = {f: _f1(per_field_stats[f]) for f in FIELDS}
    avg_f1 = sum(v[2] for v in per_field_f1.values()) / len(FIELDS)
    gate_passed = avg_f1 >= args.gate

    # ---- Markdown report ----
    lines = [
        f"# Evaluation — G1+G2 heuristic extraction — {today}",
        "",
        f"- **Dataset**: `{ds.name}`",
        f"- **Split**: `{args.split}` ({total} samples)",
        "- **OCR backend**: `rapidocr` (PP-OCRv5 via ONNX Runtime)",
        "- **Extractor**: `heuristic` (G1 regex + G2 label-anchor dictionary + column detection)",
        f"- **Wall-clock (OCR + extraction)**: {total_wall_s:.1f} s",
        "",
        "## Per-field exact-match F1",
        "",
        "| Field | Precision | Recall | F1 | Correct | Wrong | Missed | Spurious |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for field in FIELDS:
        p, r, f = per_field_f1[field]
        s = per_field_stats[field]
        lines.append(
            f"| `{field}` | {p:.3f} | {r:.3f} | **{f:.3f}** | "
            f"{s['correct']} | {s['wrong']} | {s['missed']} | {s['spurious']} |"
        )

    lines += [
        "",
        f"**Average per-field F1: {avg_f1:.3f}**",
        "",
        "## Decision gate",
        "",
        f"- Target: average per-field F1 ≥ {args.gate:.2f}",
        f"- Result: **{'PASS' if gate_passed else 'FAIL'}** "
        f"({'Component G is done — proceed to Component H (tables) and J (validation).' if gate_passed else 'Escalate to G3 (LayoutLMv3 fine-tune + OpenVINO FP32). See research.md §9.6.'})",
        "",
        "## Per-sample summary",
        "",
        "| # | ID | Correct | Wrong | Missed | Spurious | OCR ms | Extract ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for idx, r in enumerate(sample_records):
        correct = sum(1 for f in FIELDS if r["fields"][f]["outcome"] == "correct")
        wrong = sum(1 for f in FIELDS if r["fields"][f]["outcome"] == "wrong")
        missed = sum(1 for f in FIELDS if r["fields"][f]["outcome"] == "missed")
        spurious = sum(1 for f in FIELDS if r["fields"][f]["outcome"] == "spurious")
        lines.append(
            f"| {idx:02d} | `{r['id']}` | {correct}/{len(FIELDS)} | {wrong} | "
            f"{missed} | {spurious} | {r['ocr_ms']:.0f} | {r['extract_ms']:.1f} |"
        )

    lines += [
        "",
        "## Failing fields (inspection list)",
        "",
        "Lines below show where the extractor disagreed with the ground truth.",
        "First 30 failures shown; full detail in the sibling JSON.",
        "",
    ]
    failures = 0
    for r in sample_records:
        for field in FIELDS:
            fr = r["fields"][field]
            if fr["outcome"] in ("wrong", "missed") and failures < 30:
                failures += 1
                lines.append(
                    f"- `{r['id']}` / `{field}` — outcome: **{fr['outcome']}** \n"
                    f"  - predicted: `{fr['predicted']!r}`\n"
                    f"  - ground truth: `{fr['ground_truth']!r}`"
                )
    if failures == 0:
        lines.append("*No failures.*")

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- JSON report (full detail) ----
    report_json.write_text(
        json.dumps(
            {
                "date": today,
                "dataset": ds.name,
                "split": args.split,
                "sample_count": total,
                "wall_clock_s": total_wall_s,
                "gate_threshold": args.gate,
                "gate_passed": gate_passed,
                "average_f1": avg_f1,
                "per_field_stats": per_field_stats,
                "per_field_f1": {
                    f: {"precision": p, "recall": r, "f1": s}
                    for f, (p, r, s) in per_field_f1.items()
                },
                "samples": sample_records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Report (md):  {report_md}")
    print(f"Report (json): {report_json}")
    print(f"Average per-field F1: {avg_f1:.3f}")
    print(f"Gate (>= {args.gate:.2f}): {'PASS' if gate_passed else 'FAIL'}")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
