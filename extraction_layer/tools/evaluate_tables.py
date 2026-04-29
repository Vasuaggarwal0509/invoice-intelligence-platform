"""
Evaluate H1 — spatial table extractor — on katanaml.

For each sample: OCR -> SpatialTableExtractor; compare predicted items
against the Donut ground truth items array. Reports per-field F1 across
the 6 item fields, plus an item-count-accuracy metric.

Usage (PowerShell):

    python tools\\evaluate_tables.py
    python tools\\evaluate_tables.py --split test --max-samples 5
    python tools\\evaluate_tables.py --gate 0.85

Exit code: 0 if the gate passes, 1 if it fails.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from extraction_layer.components.ocr import make_ocr
from extraction_layer.components.tables import make_table_extractor
from extraction_layer.data_sources import make_dataset
from extraction_layer.data_sources.katanaml_invoices import KatanamlInvoicesDataset

ITEM_FIELDS: list[str] = [
    "item_desc",
    "item_qty",
    "item_net_price",
    "item_net_worth",
    "item_vat",
    "item_gross_worth",
]


# Numeric-valued item fields. The Donut ground truth is inconsistent on
# thousand-separator spacing (some samples have `1 319,97`, others
# `1319,97`) — we normalise internal whitespace away on both sides before
# comparing so the extractor is not penalised for matching one GT
# convention while the test answer uses the other.
_NUMERIC_FIELDS: set[str] = {
    "item_qty",
    "item_net_price",
    "item_net_worth",
    "item_vat",
    "item_gross_worth",
}


def _normalize(s: Any, field_name: str = "") -> str | None:
    if s is None:
        return None
    text = str(s).strip()
    if not text:
        return None
    if field_name in _NUMERIC_FIELDS:
        text = re.sub(r"\s+", "", text)
    return text


def _evaluate(predicted: str | None, gt: str | None, field_name: str = "") -> str:
    p = _normalize(predicted, field_name)
    g = _normalize(gt, field_name)
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
    tp = stats["correct"]
    fp = stats["wrong"] + stats["spurious"]
    fn = stats["missed"] + stats["wrong"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return precision, recall, 0.0
    return precision, recall, 2 * precision * recall / (precision + recall)


def _load_gt_items(sample) -> list[dict[str, Any]]:
    raw_items = KatanamlInvoicesDataset.items_of(sample)
    normalised: list[dict[str, Any]] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        normalised.append(
            {
                "item_desc": entry.get("item_desc"),
                "item_qty": entry.get("item_qty"),
                "item_net_price": entry.get("item_net_price"),
                "item_net_worth": entry.get("item_net_worth"),
                "item_vat": entry.get("item_vat"),
                "item_gross_worth": entry.get("item_gross_worth"),
            }
        )
    return normalised


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the spatial table extractor (H1) on a katanaml split."
    )
    parser.add_argument("--split", default="test", help="Dataset split (default: test).")
    parser.add_argument("--gate", type=float, default=0.85, help="Avg per-field F1 gate.")
    parser.add_argument(
        "--max-samples", type=int, default=None, help="Limit sample count (smoke runs)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation") / "reports",
        help="Where report files land.",
    )
    args = parser.parse_args(argv)

    today = date.today().isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_md = args.output_dir / f"{today}_H1.md"
    report_json = args.output_dir / f"{today}_H1.json"

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

    print("Loading table extractor (spatial) ...")
    extractor = make_table_extractor("spatial")

    per_field_stats: dict[str, dict[str, int]] = {
        f: {"correct": 0, "wrong": 0, "missed": 0, "spurious": 0, "both_none": 0}
        for f in ITEM_FIELDS
    }
    item_count_correct = 0
    sample_records: list[dict[str, Any]] = []

    start_all = time.perf_counter()
    for i in range(total):
        sample = ds.get(args.split, i)
        ocr_result = ocr.ocr(sample.image)
        table_result = extractor.extract(ocr_result)

        gt_items = _load_gt_items(sample)
        pred_items = [item.as_dict() for item in table_result.items]

        counts_match = len(gt_items) == len(pred_items)
        if counts_match:
            item_count_correct += 1

        n_aligned = max(len(gt_items), len(pred_items))
        per_sample_field_outcomes: list[dict[str, str]] = []

        for idx in range(n_aligned):
            gt_item = gt_items[idx] if idx < len(gt_items) else None
            pred_item = pred_items[idx] if idx < len(pred_items) else None
            outcomes: dict[str, str] = {}
            for field in ITEM_FIELDS:
                gt_val = gt_item.get(field) if gt_item is not None else None
                pred_val = pred_item.get(field) if pred_item is not None else None
                outcome = _evaluate(pred_val, gt_val, field)
                per_field_stats[field][outcome] += 1
                outcomes[field] = outcome
            per_sample_field_outcomes.append(outcomes)

        record = {
            "id": sample.id,
            "gt_item_count": len(gt_items),
            "pred_item_count": len(pred_items),
            "counts_match": counts_match,
            "per_item_outcomes": per_sample_field_outcomes,
            "predicted_items": pred_items,
            "gt_items": gt_items,
            "ocr_ms": ocr_result.duration_ms,
            "extract_ms": table_result.duration_ms,
        }
        sample_records.append(record)

        correct_fields = sum(
            1 for it in per_sample_field_outcomes for outcome in it.values() if outcome == "correct"
        )
        total_fields = len(per_sample_field_outcomes) * len(ITEM_FIELDS)
        print(
            f"  [{i:02d}] {sample.id}: items pred={len(pred_items)} gt={len(gt_items)}  "
            f"fields {correct_fields}/{total_fields}  "
            f"ocr {ocr_result.duration_ms:.0f}ms  extract {table_result.duration_ms:.1f}ms"
        )

    total_wall_s = time.perf_counter() - start_all
    per_field_f1 = {f: _f1(per_field_stats[f]) for f in ITEM_FIELDS}
    avg_f1 = sum(v[2] for v in per_field_f1.values()) / len(ITEM_FIELDS)
    item_count_accuracy = item_count_correct / total if total > 0 else 0.0
    gate_passed = avg_f1 >= args.gate

    # ---- Markdown report -----------------------------------------------------
    lines = [
        f"# Evaluation — H1 spatial table extraction — {today}",
        "",
        f"- **Dataset**: `{ds.name}`",
        f"- **Split**: `{args.split}` ({total} samples)",
        "- **OCR backend**: `rapidocr` (PP-OCRv5 via ONNX Runtime)",
        "- **Table extractor**: `spatial` (H1 — value-pattern row clustering)",
        f"- **Wall-clock (OCR + extraction)**: {total_wall_s:.1f} s",
        "",
        "## Item-count accuracy",
        "",
        f"- Invoices where predicted item count == GT item count: "
        f"**{item_count_correct}/{total}** ({item_count_accuracy:.1%})",
        "",
        "## Per-field exact-match F1 (across every item position across every sample)",
        "",
        "| Field | Precision | Recall | F1 | Correct | Wrong | Missed | Spurious |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for field in ITEM_FIELDS:
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
        f"({'Component H1 is done — proceed to Component J (validation).' if gate_passed else 'Revisit H1 algorithm or escalate to H2 (img2table) / H3 (PP-StructureV3). See research.md §10.'})",
        "",
        "## Per-sample summary",
        "",
        "| # | ID | Pred # | GT # | Counts OK | Fields OK | OCR ms | Extract ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for idx, r in enumerate(sample_records):
        correct = sum(
            1 for it in r["per_item_outcomes"] for outcome in it.values() if outcome == "correct"
        )
        total_fields = len(r["per_item_outcomes"]) * len(ITEM_FIELDS)
        lines.append(
            f"| {idx:02d} | `{r['id']}` | {r['pred_item_count']} | {r['gt_item_count']} | "
            f"{'yes' if r['counts_match'] else 'NO'} | "
            f"{correct}/{total_fields} | "
            f"{r['ocr_ms']:.0f} | {r['extract_ms']:.1f} |"
        )

    lines += [
        "",
        "## Failing samples (inspection list — first 20)",
        "",
    ]
    failing_count = 0
    for r in sample_records:
        all_correct = all(
            outcome == "correct" for it in r["per_item_outcomes"] for outcome in it.values()
        )
        if all_correct and r["counts_match"]:
            continue
        if failing_count >= 20:
            break
        failing_count += 1
        lines.append(
            f"### `{r['id']}` — predicted {r['pred_item_count']} item(s), GT {r['gt_item_count']}"
        )
        for item_idx, outcomes in enumerate(r["per_item_outcomes"]):
            pred = r["predicted_items"][item_idx] if item_idx < len(r["predicted_items"]) else None
            gt = r["gt_items"][item_idx] if item_idx < len(r["gt_items"]) else None
            bad_fields = [f for f, o in outcomes.items() if o not in ("correct", "both_none")]
            if not bad_fields:
                continue
            lines.append(f"- item[{item_idx}] wrong fields: {bad_fields}")
            for f in bad_fields:
                p_v = pred.get(f) if pred else None
                g_v = gt.get(f) if gt else None
                lines.append(f"  - `{f}`: pred=`{p_v!r}`  gt=`{g_v!r}`")
        lines.append("")
    if failing_count == 0:
        lines.append("*No failing samples.*")

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- JSON report ---------------------------------------------------------
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
                "item_count_accuracy": item_count_accuracy,
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
    print(f"Report (md):   {report_md}")
    print(f"Report (json): {report_json}")
    print(f"Item-count accuracy: {item_count_correct}/{total} ({item_count_accuracy:.1%})")
    print(f"Average per-field F1: {avg_f1:.3f}")
    print(f"Gate (>= {args.gate:.2f}): {'PASS' if gate_passed else 'FAIL'}")
    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
