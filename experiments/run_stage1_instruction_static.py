"""Stage 1 instruction-conditioned static extension CLI.

Usage:
    python -m experiments.run_stage1_instruction_static
    python -m experiments.run_stage1_instruction_static --events 2024061623
    python -m experiments.run_stage1_instruction_static --release-family joint_driven_release
    python -m experiments.run_stage1_instruction_static --operation-interval 6
    python -m experiments.run_stage1_instruction_static --output experiments/results/stage1_instruction_static
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from experiments.stage1.instruction_static import (
    RELEASE_FAMILIES,
    InstructionStaticRunner,
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


def _write_summaries(results: list[dict[str, Any]], output_dir: Path) -> None:
    if not results:
        return

    df = pd.DataFrame(results)
    summary_dir = output_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    # By release family
    if "specified_release_family" in df.columns:
        fam_agg = (
            df.groupby("specified_release_family")
            .agg(
                total=("event_id", "count"),
                accepted=("accepted", "sum"),
                command_compliance=("command_compliance", "sum"),
                interval_compliance=("interval_compliance", "sum"),
                hard_violations=("hard_violation", "sum"),
                downstream_violations=("downstream_violation", "sum"),
                mean_max_level=("max_level", "mean"),
                mean_terminal_deviation=("terminal_deviation", "mean"),
                mean_peak_reduction=("peak_reduction_rate", "mean"),
            )
            .reset_index()
        )
        fam_agg.to_csv(summary_dir / "by_release_family.csv", index=False)

    # By operation interval
    if "operation_interval_h" in df.columns:
        int_agg = (
            df.groupby("operation_interval_h")
            .agg(
                total=("event_id", "count"),
                accepted=("accepted", "sum"),
                command_compliance=("command_compliance", "sum"),
                interval_compliance=("interval_compliance", "sum"),
                hard_violations=("hard_violation", "sum"),
            )
            .reset_index()
        )
        int_agg.to_csv(summary_dir / "by_operation_interval.csv", index=False)

    # By flood group
    if "scenario_group" in df.columns:
        grp_agg = (
            df.groupby("scenario_group")
            .agg(
                total=("event_id", "count"),
                accepted=("accepted", "sum"),
                hard_violations=("hard_violation", "sum"),
                mean_max_level=("max_level", "mean"),
                mean_terminal_deviation=("terminal_deviation", "mean"),
            )
            .reset_index()
        )
        grp_agg.to_csv(summary_dir / "by_flood_group.csv", index=False)

    # Failure taxonomy
    failed = df[df["accepted"] == False]  # noqa: E712
    if "failure_reason" in failed.columns and not failed.empty:
        taxonomy = (
            failed.groupby("failure_reason")
            .agg(count=("event_id", "count"))
            .reset_index()
        )
        taxonomy.to_csv(summary_dir / "failure_taxonomy.csv", index=False)

    # JSON metrics
    total = len(df)
    accepted_count = int(df["accepted"].sum()) if "accepted" in df.columns else 0
    cmd_compliance = int(df["command_compliance"].sum()) if "command_compliance" in df.columns else 0
    int_compliance = int(df["interval_compliance"].sum()) if "interval_compliance" in df.columns else 0
    hard_viol = int(df["hard_violation"].sum()) if "hard_violation" in df.columns else 0
    ds_viol = int(df["downstream_violation"].sum()) if "downstream_violation" in df.columns else 0

    metrics: dict[str, Any] = {
        "extension_type": "instruction_conditioned_static",
        "total_attempted": total,
        "accepted_count": accepted_count,
        "acceptance_rate": round(accepted_count / total, 4) if total else 0,
        "command_compliance_count": cmd_compliance,
        "command_compliance_rate": round(cmd_compliance / total, 4) if total else 0,
        "interval_compliance_count": int_compliance,
        "interval_compliance_rate": round(int_compliance / total, 4) if total else 0,
        "hard_violation_count": hard_viol,
        "downstream_violation_count": ds_viol,
        "mean_max_level": round(float(df["max_level"].mean()), 3) if "max_level" in df.columns else None,
        "mean_terminal_deviation": round(float(df["terminal_deviation"].mean()), 3) if "terminal_deviation" in df.columns else None,
        "mean_peak_reduction_rate": round(float(df["peak_reduction_rate"].mean()), 4) if "peak_reduction_rate" in df.columns else None,
    }
    (summary_dir / "instruction_static_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Trajectories (per-event stub)
    traj_dir = output_dir / "trajectories"
    traj_dir.mkdir(parents=True, exist_ok=True)
    for _, row in df.iterrows():
        stub = {
            "event_id": row.get("event_id"),
            "specified_release_family": row.get("specified_release_family"),
            "operation_interval_h": row.get("operation_interval_h"),
            "max_level": row.get("max_level"),
            "terminal_level": row.get("terminal_level"),
            "peak_inflow": row.get("peak_inflow"),
            "peak_release": row.get("peak_release"),
            "accepted": row.get("accepted"),
        }
        fname = f"{row.get('event_id')}_{row.get('specified_release_family')}_{row.get('operation_interval_h')}h.json"
        (traj_dir / fname).write_text(json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_markdown_summary(results: list[dict[str, Any]], output_dir: Path) -> None:
    df = pd.DataFrame(results) if results else pd.DataFrame()
    total = len(df)
    accepted = int(df["accepted"].sum()) if "accepted" in df.columns and total else 0
    cmd = int(df["command_compliance"].sum()) if "command_compliance" in df.columns and total else 0
    ivl = int(df["interval_compliance"].sum()) if "interval_compliance" in df.columns and total else 0
    hv = int(df["hard_violation"].sum()) if "hard_violation" in df.columns and total else 0
    dv = int(df["downstream_violation"].sum()) if "downstream_violation" in df.columns and total else 0

    lines = [
        "# Stage 1 Instruction-Conditioned Static Extension — Tankeng Reservoir",
        "",
        "Extension type: `instruction_conditioned_static`  ",
        "Workflow type: `stage1_direct_service`  ",
        f"Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Total attempted | {total} |",
        f"| Accepted | {accepted} ({round(accepted/total*100,1) if total else 0}%) |",
        f"| Command compliance | {cmd} ({round(cmd/total*100,1) if total else 0}%) |",
        f"| Interval compliance | {ivl} ({round(ivl/total*100,1) if total else 0}%) |",
        f"| Hard violations | {hv} |",
        f"| Downstream violations | {dv} |",
        "",
        "## Notes",
        "",
        "- Release family and operation interval are specified by operator command.",
        "- All metrics are computed after block-mean quantization and re-simulation.",
        "- This extension does not compare against historical Tankeng operation.",
        "- See `summary/` for breakdowns by release family, operation interval, and flood group.",
    ]
    (output_dir / "STAGE1_INSTRUCTION_STATIC_SUMMARY.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage 1 instruction-conditioned static extension"
    )
    parser.add_argument("--events", nargs="*", default=None)
    parser.add_argument("--release-family", nargs="*", default=None, dest="release_family")
    parser.add_argument("--operation-interval", nargs="*", type=int, default=None, dest="operation_interval")
    parser.add_argument("--output", default="experiments/results/stage1_instruction_static")
    parser.add_argument("--config", default="experiments/config/stage1_instruction_static.yml")
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

    data_root = config.get("data", {}).get("root", "data")
    runner = InstructionStaticRunner(data_root=data_root)

    total_runs = len(events) * len(families) * len(intervals)
    if args.verbose:
        print(f"Running instruction-conditioned static extension:")
        print(f"  Events: {len(events)}, Families: {len(families)}, Intervals: {intervals}")
        print(f"  Total runs: {total_runs}")

    results: list[dict[str, Any]] = []
    run_num = 0
    for event_id in events:
        for family in families:
            for interval_h in intervals:
                run_num += 1
                if args.verbose:
                    print(f"  [{run_num}/{total_runs}] {event_id} | {family} | {interval_h}h ...", end=" ", flush=True)
                try:
                    row = runner.run_instruction_static(event_id, family, interval_h)
                    results.append(row)
                    if args.verbose:
                        status = "OK" if row.get("accepted") else "FAIL"
                        cc = "CC" if row.get("command_compliance") else "nc"
                        ic = "IC" if row.get("interval_compliance") else "ni"
                        print(f"{status} {cc} {ic} | max_level={row.get('max_level')}")
                except Exception as exc:
                    if args.verbose:
                        print(f"ERROR: {exc}")
                    results.append({
                        "event_id": event_id,
                        "specified_release_family": family,
                        "operation_interval_h": interval_h,
                        "accepted": False,
                        "failure_reason": str(exc),
                    })

    if results:
        df = pd.DataFrame(results)
        df.to_csv(output_dir / "results.csv", index=False)

    _write_summaries(results, output_dir)
    _write_markdown_summary(results, output_dir)

    if args.verbose:
        accepted = sum(1 for r in results if r.get("accepted"))
        print(f"\nDone. {len(results)} rows, {accepted} accepted → {output_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
