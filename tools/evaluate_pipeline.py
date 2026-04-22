"""
End-to-end pipeline evaluation for katanaml.

For each sample in the chosen split this CLI runs:

  OCR  ->  heuristic extraction  ->  spatial table extraction  ->  validation

and reports **per-rule pass rate** plus **per-sample all-checks-pass
rate** on the batch. Writes a dated report to
``evaluation/reports/YYYY-MM-DD_pipeline.md`` (and a sibling ``.json``).

Usage (PowerShell):

    python tools\\evaluate_pipeline.py
    python tools\\evaluate_pipeline.py --split validation --max-samples 5
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from components.extraction import make_extractor
from components.ocr import make_ocr
from components.tables import make_table_extractor
from components.validation import RuleOutcome, ValidationEngine
from data_sources import make_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end pipeline evaluation (OCR -> extraction -> tables -> validation) on katanaml."
    )
    parser.add_argument("--split", default="test", help="Dataset split (default: test).")
    parser.add_argument("--max-samples", type=int, default=None, help="Limit sample count.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation") / "reports",
        help="Where report files land.",
    )
    args = parser.parse_args(argv)

    today = date.today().isoformat()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_md = args.output_dir / f"{today}_pipeline.md"
    report_json = args.output_dir / f"{today}_pipeline.json"

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

    print("Loading extractors + validation engine ...")
    extractor = make_extractor("heuristic")
    table_extractor = make_table_extractor("spatial")
    engine = ValidationEngine()

    per_rule_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"pass": 0, "fail": 0, "not_applicable": 0}
    )
    sample_records: list[dict[str, Any]] = []
    extractions = []
    tables_list = []

    start_all = time.perf_counter()
    for i in range(total):
        sample = ds.get(args.split, i)
        ocr_result = ocr.ocr(sample.image)
        extraction = extractor.extract(ocr_result)
        tables = table_extractor.extract(ocr_result)
        extractions.append(extraction)
        tables_list.append(tables)

        sample_records.append(
            {
                "id": sample.id,
                "ocr_ms": ocr_result.duration_ms,
                "extract_ms": extraction.duration_ms,
                "tables_ms": tables.duration_ms,
                "item_count_pred": len(tables.items),
            }
        )
        print(
            f"  [{i:02d}] {sample.id}: "
            f"OCR {ocr_result.duration_ms:.0f}ms  "
            f"extract {extraction.duration_ms:.1f}ms  "
            f"tables {tables.duration_ms:.1f}ms  "
            f"items {len(tables.items)}"
        )

    print("\nRunning validation engine (batch mode — enables duplicate detection) ...")
    validation_results = engine.validate_batch(extractions, tables_list)

    # Aggregate per-rule outcomes
    all_checks_pass_count = 0
    for record, vr in zip(sample_records, validation_results):
        record["validation_summary"] = vr.summary()
        record["validation_failures"] = [
            {
                "rule": f.rule_name,
                "target": f.target,
                "reason": f.reason,
                "expected": f.expected,
                "observed": f.observed,
            }
            for f in vr.failures()
        ]
        record["all_checks_pass"] = vr.all_checks_pass()
        if vr.all_checks_pass():
            all_checks_pass_count += 1
        for finding in vr.findings:
            key = finding.outcome.value  # "pass" / "fail" / "not_applicable"
            per_rule_stats[finding.rule_name][key] += 1

    total_wall_s = time.perf_counter() - start_all
    clean_pct = all_checks_pass_count / total if total > 0 else 0.0

    # ---- Markdown report ----
    lines = [
        f"# End-to-end pipeline evaluation — {today}",
        "",
        f"- **Dataset**: `{ds.name}`",
        f"- **Split**: `{args.split}` ({total} samples)",
        "- **Pipeline**: OCR (rapidocr) -> extraction (heuristic) -> tables (spatial) -> validation (engine)",
        f"- **Wall-clock**: {total_wall_s:.1f} s",
        "",
        "## Clean-invoice rate",
        "",
        f"- Invoices where **every applicable validation rule passed**: "
        f"**{all_checks_pass_count}/{total}** ({clean_pct:.1%})",
        "",
        "## Per-rule outcomes",
        "",
        "| Rule | Pass | Fail | N/A | Pass rate (pass / (pass+fail)) |",
        "|---|---|---|---|---|",
    ]
    for rule, counts in sorted(per_rule_stats.items()):
        decisive = counts["pass"] + counts["fail"]
        rate = counts["pass"] / decisive if decisive > 0 else 0.0
        lines.append(
            f"| `{rule}` | {counts['pass']} | {counts['fail']} | {counts['not_applicable']} | "
            f"{rate:.3f} |"
        )

    lines += [
        "",
        "## Per-sample summary",
        "",
        "| # | ID | All pass | Pass | Fail | N/A | Items | OCR ms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for idx, r in enumerate(sample_records):
        s = r["validation_summary"]
        lines.append(
            f"| {idx:02d} | `{r['id']}` | "
            f"{'YES' if r['all_checks_pass'] else 'no'} | "
            f"{s['pass']} | {s['fail']} | {s['not_applicable']} | "
            f"{r['item_count_pred']} | {r['ocr_ms']:.0f} |"
        )

    lines += [
        "",
        "## Failing rules (inspection list — first 25 failures)",
        "",
    ]
    shown = 0
    for r in sample_records:
        for fail in r["validation_failures"]:
            if shown >= 25:
                break
            shown += 1
            exp_part = f"  expected=`{fail['expected']!r}`" if fail["expected"] else ""
            obs_part = f"  observed=`{fail['observed']!r}`" if fail["observed"] else ""
            lines.append(
                f"- `{r['id']}` / `{fail['rule']}` @ `{fail['target']}` — {fail['reason']}"
                f"{exp_part}{obs_part}"
            )
        if shown >= 25:
            break
    if shown == 0:
        lines.append("*No validation failures.*")

    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report_json.write_text(
        json.dumps(
            {
                "date": today,
                "dataset": ds.name,
                "split": args.split,
                "sample_count": total,
                "wall_clock_s": total_wall_s,
                "clean_invoice_rate": clean_pct,
                "per_rule_stats": per_rule_stats,
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
    print(f"Clean-invoice rate: {all_checks_pass_count}/{total} ({clean_pct:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
