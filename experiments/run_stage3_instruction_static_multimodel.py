"""Run Stage 3 instruction-static evaluation for multiple models in parallel.

Launches mimo_v25, minimax_m2_5_free, and claude_haiku_4_5 simultaneously,
waits for all to finish, then writes a combined cross-model comparison report.

Usage:
    python -m experiments.run_stage3_instruction_static_multimodel
    python -m experiments.run_stage3_instruction_static_multimodel --compare
    python -m experiments.run_stage3_instruction_static_multimodel --models mimo_v25 claude_haiku_4_5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


MODELS: list[tuple[str, str]] = [
    ("mimo_v25",           "experiments/results/stage3_instruction_static_mimo_subset"),
    ("minimax_m2_5_free",  "experiments/results/stage3_instruction_static_minimax_subset"),
    ("claude_haiku_4_5",   "experiments/results/stage3_instruction_static_claude_subset"),
]

EVENTS_FILE = "experiments/config/stage3_instruction_static_representative_events.txt"
STAGE2_DIR  = "experiments/results/stage2_instruction_static"
CONFIG      = "experiments/config/stage3_instruction_static.yml"


def _launch(model_profile: str, output_dir: str) -> subprocess.Popen:
    """Launch the evaluation run (no --compare; comparison runs after all models finish)."""
    cmd = [
        sys.executable, "-m", "experiments.run_stage3_instruction_static",
        "--events-file", EVENTS_FILE,
        "--model-profile", model_profile,
        "--output", output_dir,
        "--config", CONFIG,
        "--verbose",
    ]
    log_path = Path(output_dir) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w", encoding="utf-8")
    print(f"  [{model_profile}] → {output_dir}/  (log: {log_path})")
    return subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, text=True)


def _launch_compare(model_profile: str, output_dir: str) -> subprocess.Popen:
    """Launch comparison against Stage 2 oracle (non-blocking)."""
    cmd = [
        sys.executable, "-m", "experiments.run_stage3_instruction_static",
        "--compare",
        "--stage2-dir", STAGE2_DIR,
        "--output", output_dir,
        "--config", CONFIG,
        "--verbose",
    ]
    log_path = Path(output_dir) / "compare.log"
    log_file = open(log_path, "w", encoding="utf-8")
    print(f"  [{model_profile}] comparing against Stage 2 oracle...")
    return subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, text=True)


def _wait_all(procs: list[tuple[str, subprocess.Popen]]) -> dict[str, int]:
    """Poll until all processes finish; return {model: returncode}."""
    remaining = list(procs)
    done: dict[str, int] = {}
    while remaining:
        still_running = []
        for model, p in remaining:
            rc = p.poll()
            if rc is None:
                still_running.append((model, p))
            else:
                done[model] = rc
                status = "OK" if rc == 0 else f"FAILED(rc={rc})"
                print(f"  [{model}] finished — {status}")
        remaining = still_running
        if remaining:
            time.sleep(5)
    return done


def _load_metrics(output_dir: str) -> dict[str, Any] | None:
    p = Path(output_dir) / "summary" / "instruction_static_stage3_metrics.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _load_comparison(output_dir: str) -> dict[str, Any] | None:
    p = Path(output_dir) / "comparison" / "instruction_static_comparison_report.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _build_combined_report(
    models: list[tuple[str, str]],
    returncodes: dict[str, int],
    compare: bool,
) -> dict[str, Any]:
    rows = []
    for model_profile, output_dir in models:
        m = _load_metrics(output_dir) or {}
        c = _load_comparison(output_dir) if compare else None
        row: dict[str, Any] = {
            "model_profile": model_profile,
            "output_dir": output_dir,
            "exit_code": returncodes.get(model_profile, -1),
            "total_attempted": m.get("total_attempted", 0),
            "accepted_count": m.get("accepted_count", 0),
            "acceptance_rate": m.get("acceptance_rate", 0.0),
            "command_compliance_rate": m.get("command_compliance_rate", 0.0),
            "interval_compliance_rate": m.get("interval_compliance_rate", 0.0),
            "hard_violation_count": m.get("hard_violation_count", 0),
            "downstream_violation_count": m.get("downstream_violation_count", 0),
            "tool_order_validity_rate": m.get("tool_order_validity_rate", 0.0),
            "eval_ref_validity_rate": m.get("eval_ref_validity_rate", 0.0),
            "schema_validity_rate": m.get("schema_validity_rate", 0.0),
        }
        if compare and c:
            row["passes_oracle"] = c.get("passes_oracle")
            row["cc_mismatches"] = c.get("command_compliance_mismatches", 0)
            row["ic_mismatches"] = c.get("interval_compliance_mismatches", 0)
            row["matched_rows"] = c.get("matched_rows", 0)
        rows.append(row)
    return {"models": rows, "events_file": EVENTS_FILE, "stage2_oracle_dir": STAGE2_DIR if compare else None}


def _write_combined_report(report: dict[str, Any], out_dir: Path, compare: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cross_model_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    rows = report["models"]
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "cross_model_summary.csv", index=False)

    import datetime
    lines = [
        "# Stage 3 Instruction-Static — Cross-Model Comparison",
        "",
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Events file: `{report['events_file']}`",
        "",
        "> **Note:** Stage 3 LLM evaluation was run on a representative 8-event subset "
        "(96 rows). Full 492-row deterministic coverage is in Stage 1 and Stage 2.",
        "",
        "## Results",
        "",
    ]

    # Build header
    cols = ["model_profile", "total_attempted", "acceptance_rate",
            "command_compliance_rate", "interval_compliance_rate",
            "tool_order_validity_rate", "eval_ref_validity_rate", "schema_validity_rate"]
    if compare:
        cols += ["passes_oracle", "cc_mismatches", "ic_mismatches"]

    header = "| " + " | ".join(c.replace("_", " ") for c in cols) + " |"
    sep    = "| " + " | ".join("---" for _ in cols) + " |"
    lines += [header, sep]

    for r in rows:
        def _fmt(v: Any) -> str:
            if isinstance(v, float):
                return f"{v:.4f}"
            if v is None:
                return "—"
            return str(v)
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")

    lines += ["", "## Per-Model Failure Taxonomy", ""]
    for model_profile, output_dir in [(r["model_profile"], r["output_dir"]) for r in rows]:
        tax_path = Path(output_dir) / "summary" / "failure_taxonomy.csv"
        lines.append(f"### {model_profile}")
        if tax_path.exists():
            tax_df = pd.read_csv(tax_path)
            lines.append("")
            lines.append("| Failure Reason | Count |")
            lines.append("|----------------|-------|")
            for _, row in tax_df.iterrows():
                lines.append(f"| {row['failure_reason']} | {row['count']} |")
        else:
            lines.append("_No failures or taxonomy not available._")
        lines.append("")

    (out_dir / "CROSS_MODEL_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nCombined report written to {out_dir}/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stage 3 instruction-static for multiple models in parallel")
    parser.add_argument("--models", nargs="*", default=None,
                        help="Model profiles to run (default: all three)")
    parser.add_argument("--compare", action="store_true", default=False,
                        help="Compare each model against Stage 2 oracle after running")
    parser.add_argument("--report-only", action="store_true", default=False, dest="report_only",
                        help="Skip model runs; just regenerate combined report from existing results")
    parser.add_argument("--combined-output", default="experiments/results/stage3_instruction_static_combined",
                        dest="combined_output")
    args = parser.parse_args(argv)

    selected_models = [
        (m, d) for m, d in MODELS
        if args.models is None or m in args.models
    ]
    if not selected_models:
        print("No matching models found.")
        return 1

    if args.report_only:
        returncodes = {m: 0 for m, _ in selected_models}
        report = _build_combined_report(selected_models, returncodes, args.compare)
        _write_combined_report(report, Path(args.combined_output), args.compare)
        print("\n=== Cross-Model Summary ===")
        print(f"{'Model':<28} {'Total':>6} {'Accepted':>9} {'CC':>7} {'IC':>7}")
        print("-" * 62)
        for r in report["models"]:
            total = r["total_attempted"]
            acc   = r["accepted_count"]
            cc    = round(r["command_compliance_rate"] * 100, 1)
            ic    = round(r["interval_compliance_rate"] * 100, 1)
            print(f"{r['model_profile']:<28} {total:>6} {acc:>9} {cc:>6}% {ic:>6}%")
        return 0

    print(f"Launching {len(selected_models)} model(s) in parallel:")
    procs: list[tuple[str, subprocess.Popen]] = []
    for model_profile, output_dir in selected_models:
        p = _launch(model_profile, output_dir)
        procs.append((model_profile, p))

    print(f"\nWaiting for all runs to complete...")
    returncodes = _wait_all(procs)

    failed = [m for m, rc in returncodes.items() if rc != 0]
    if failed:
        print(f"\nWARNING: {len(failed)} model(s) exited with errors: {failed}")

    if args.compare:
        print("\nRunning oracle comparisons in parallel...")
        cmp_procs: list[tuple[str, subprocess.Popen]] = []
        for model_profile, output_dir in selected_models:
            if returncodes.get(model_profile, -1) == 0:
                p = _launch_compare(model_profile, output_dir)
                cmp_procs.append((model_profile, p))
        if cmp_procs:
            _wait_all(cmp_procs)

    report = _build_combined_report(selected_models, returncodes, args.compare)
    _write_combined_report(report, Path(args.combined_output), args.compare)

    # Print quick summary table
    print("\n=== Cross-Model Summary ===")
    print(f"{'Model':<28} {'Total':>6} {'Accepted':>9} {'CC':>7} {'IC':>7}")
    print("-" * 62)
    for r in report["models"]:
        total = r["total_attempted"]
        acc   = r["accepted_count"]
        cc    = round(r["command_compliance_rate"] * 100, 1)
        ic    = round(r["interval_compliance_rate"] * 100, 1)
        print(f"{r['model_profile']:<28} {total:>6} {acc:>9} {cc:>6}% {ic:>6}%")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
