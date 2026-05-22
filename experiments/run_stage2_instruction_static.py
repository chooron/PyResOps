"""Stage 2 instruction-conditioned static extension CLI.

Usage:
    python -m experiments.run_stage2_instruction_static --output experiments/results/stage2_instruction_static
    python -m experiments.run_stage2_instruction_static --compare --stage1-dir experiments/results/stage1_instruction_static --output experiments/results/stage2_instruction_static
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from experiments.stage1.instruction_static import RELEASE_FAMILIES
from experiments.stage2.instruction_static_workflow import (
    InstructionStaticComparator,
    InstructionStaticWorkflow,
)


def _load_event_list(path: str) -> list[str]:
    events: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            event_id = line.split("|")[0].strip()
            if event_id:
                events.append(event_id)
    return events


def _run_workflow(
    config: dict,
    events: list[str],
    families: list[str],
    intervals: list[int],
    output_dir: Path,
    verbose: bool,
) -> list[dict[str, Any]]:
    data_root = config.get("data", {}).get("root", "data")
    workflow = InstructionStaticWorkflow(data_root=data_root)

    total_runs = len(events) * len(families) * len(intervals)
    if verbose:
        print(f"Stage 2 workflow replication:")
        print(f"  Events: {len(events)}, Families: {len(families)}, Intervals: {intervals}")
        print(f"  Total runs: {total_runs}")

    results: list[dict[str, Any]] = []
    run_num = 0
    for event_id in events:
        for family in families:
            for interval_h in intervals:
                run_num += 1
                if verbose:
                    print(f"  [{run_num}/{total_runs}] {event_id} | {family} | {interval_h}h ...", end=" ", flush=True)
                try:
                    row = workflow.run(event_id, family, interval_h)
                    results.append(row)
                    if verbose:
                        status = "OK" if row.get("accepted") else "FAIL"
                        cc = "CC" if row.get("command_compliance") else "nc"
                        ic = "IC" if row.get("interval_compliance") else "ni"
                        print(f"{status} {cc} {ic} | max_level={row.get('max_level')}")
                except Exception as exc:
                    if verbose:
                        print(f"ERROR: {exc}")
                    results.append({
                        "event_id": event_id,
                        "specified_release_family": family,
                        "operation_interval_h": interval_h,
                        "accepted": False,
                        "failure_reason": str(exc),
                        "workflow_type": "stage2_workflow",
                    })

    if results:
        df = pd.DataFrame(results)
        # Drop tool_trace from CSV to keep it readable
        save_cols = [c for c in df.columns if c != "tool_trace"]
        df[save_cols].to_csv(output_dir / "results.csv", index=False)

    return results


def _run_comparison(
    stage1_dir: Path,
    stage2_dir: Path,
    verbose: bool,
) -> dict[str, Any]:
    comparator = (
        InstructionStaticComparator()
        .load_stage1(stage1_dir)
        .load_stage2(stage2_dir)
    )
    report = comparator.compare()

    comparison_dir = stage2_dir / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    # Comparison CSV
    s1_csv = stage1_dir / "results.csv"
    s2_csv = stage2_dir / "results.csv"
    if s1_csv.exists() and s2_csv.exists():
        s1 = pd.read_csv(s1_csv)
        s2 = pd.read_csv(s2_csv)
        align_keys = ["event_id", "specified_release_family", "operation_interval_h"]
        for df in (s1, s2):
            for k in align_keys:
                if k not in df.columns:
                    df[k] = ""
        merged = s1.merge(s2, on=align_keys, suffixes=("_s1", "_s2"), how="outer", indicator=True)
        merged.to_csv(comparison_dir / "stage2_vs_stage1_instruction_static_comparison.csv", index=False)

        # Failure taxonomy
        failed = merged[merged.get("accepted_s2", merged.get("accepted", pd.Series(dtype=bool))) == False]  # noqa: E712
        if "failure_reason_s2" in failed.columns and not failed.empty:
            taxonomy = (
                failed.groupby("failure_reason_s2")
                .agg(count=("event_id", "count"))
                .reset_index()
            )
            taxonomy.to_csv(comparison_dir / "failure_taxonomy.csv", index=False)

    summary_dir = stage2_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "instruction_static_stage2_metrics.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return report


def _write_markdown_summary(
    results: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
    output_dir: Path,
) -> None:
    df = pd.DataFrame(results) if results else pd.DataFrame()
    total = len(df)
    accepted = int(df["accepted"].sum()) if "accepted" in df.columns and total else 0

    lines = [
        "# Stage 2 Instruction-Conditioned Static Extension — Tankeng Reservoir",
        "",
        "Extension type: `instruction_conditioned_static`  ",
        "Workflow type: `stage2_workflow`  ",
        f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Stage 2 Replication Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total rows | {total} |",
        f"| Accepted | {accepted} |",
    ]

    if comparison:
        lines += [
            "",
            "## Oracle Comparison",
            "",
            f"| Metric | Value |",
            f"|---|---|",
            f"| Stage 1 rows | {comparison.get('s1_total', '-')} |",
            f"| Stage 2 rows | {comparison.get('s2_total', '-')} |",
            f"| Matched rows | {comparison.get('matched_rows', '-')} |",
            f"| Missing in Stage 2 | {comparison.get('missing_in_s2', '-')} |",
            f"| Extra in Stage 2 | {comparison.get('extra_in_s2', '-')} |",
            f"| Accepted mismatches | {comparison.get('accepted_mismatch', '-')} |",
            f"| max_level tolerance failures | {comparison.get('max_level_failures', '-')} |",
            f"| terminal_deviation failures | {comparison.get('terminal_deviation_failures', '-')} |",
            f"| peak_reduction failures | {comparison.get('peak_reduction_failures', '-')} |",
            f"| command_compliance mismatches | {comparison.get('command_compliance_mismatches', '-')} |",
            f"| interval_compliance mismatches | {comparison.get('interval_compliance_mismatches', '-')} |",
            f"| **Passes oracle** | **{comparison.get('passes_oracle', False)}** |",
        ]

    lines += [
        "",
        "## Notes",
        "",
        "- Stage 2 executes workflow-style steps directly (not delegating to Stage 1 runner).",
        "- All metrics are computed after block-mean quantization and re-simulation.",
        "- Oracle tolerances: max_level ±0.5 m, terminal_deviation ±0.5 m, peak_reduction_rate ±0.05.",
    ]

    (output_dir / "STAGE2_INSTRUCTION_STATIC_SUMMARY.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage 2 instruction-conditioned static extension"
    )
    parser.add_argument("--compare", action="store_true", default=False)
    parser.add_argument("--stage1-dir", default="experiments/results/stage1_instruction_static", dest="stage1_dir")
    parser.add_argument("--events", nargs="*", default=None)
    parser.add_argument("--release-family", nargs="*", default=None, dest="release_family")
    parser.add_argument("--operation-interval", nargs="*", type=int, default=None, dest="operation_interval")
    parser.add_argument("--output", default="experiments/results/stage2_instruction_static")
    parser.add_argument("--config", default="experiments/config/stage2_instruction_static.yml")
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    event_list_path = config.get("data", {}).get("event_list", "experiments/config/stage1_event_list_41.txt")
    all_events = _load_event_list(event_list_path)
    events = args.events or all_events
    families = args.release_family or config.get("release_families", RELEASE_FAMILIES)
    intervals = args.operation_interval or config.get("operation_intervals_h", [6, 12])

    results = _run_workflow(config, events, families, intervals, output_dir, args.verbose)

    comparison: dict[str, Any] | None = None
    if args.compare:
        stage1_dir = Path(args.stage1_dir)
        if not (stage1_dir / "results.csv").exists():
            print(f"Stage 1 oracle not found at {stage1_dir}/results.csv — skipping comparison.")
        else:
            comparison = _run_comparison(stage1_dir, output_dir, args.verbose)
            if args.verbose:
                print(f"\nOracle comparison: passes_oracle={comparison.get('passes_oracle')}")
                print(f"  matched={comparison.get('matched_rows')} missing={comparison.get('missing_in_s2')} extra={comparison.get('extra_in_s2')}")

    _write_markdown_summary(results, comparison, output_dir)

    if args.verbose:
        accepted = sum(1 for r in results if r.get("accepted"))
        print(f"\nDone. {len(results)} rows, {accepted} accepted → {output_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
