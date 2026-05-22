"""Stage 3 instruction-conditioned static extension CLI.

Usage:
    # Smoke test (1 event × 6 families × 2 intervals = 12 rows)
    python -m experiments.run_stage3_instruction_static --events 2024061623 --model-profile mimo_v25 --output experiments/results/stage3_instruction_static_mimo_smoke

    # Representative subset (8 events × 6 families × 2 intervals = 96 rows)
    python -m experiments.run_stage3_instruction_static --events-file experiments/config/stage3_instruction_static_representative_events.txt --model-profile mimo_v25 --output experiments/results/stage3_instruction_static_mimo_subset

    # Full MiMo run (41 events × 6 families × 2 intervals = 492 rows)
    python -m experiments.run_stage3_instruction_static --model-profile mimo_v25 --output experiments/results/stage3_instruction_static_mimo

    # Compare against Stage 2 extension oracle (subset-aware)
    python -m experiments.run_stage3_instruction_static --compare --stage2-dir experiments/results/stage2_instruction_static --output experiments/results/stage3_instruction_static_mimo_subset
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from experiments.stage1.instruction_static import RELEASE_FAMILIES
from experiments.stage3.instruction_static_runner import InstructionStaticLlmRunner


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


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _run_matrix(
    config: dict,
    events: list[str],
    families: list[str],
    intervals: list[int],
    output_dir: Path,
    model_profile: str,
    verbose: bool,
) -> list[dict[str, Any]]:
    data_root = config.get("data", {}).get("root", "data")
    traces_dir = str(output_dir / "traces")

    runner = InstructionStaticLlmRunner(
        model_profile=model_profile,
        config_path=config.get("llm_config_path"),
        paper_config=config,
        data_root=data_root,
        traces_dir=traces_dir,
    )

    total = len(events) * len(families) * len(intervals)
    if verbose:
        print(f"Stage 3 instruction-conditioned static extension:")
        print(f"  Model: {model_profile}")
        print(f"  Events: {len(events)}, Families: {len(families)}, Intervals: {intervals}")
        print(f"  Total runs: {total}")

    results: list[dict[str, Any]] = []
    run_num = 0
    try:
        for event_id in events:
            for family in families:
                for interval_h in intervals:
                    run_num += 1
                    if verbose:
                        print(
                            f"  [{run_num}/{total}] {event_id} | {family} | {interval_h}h ...",
                            end=" ",
                            flush=True,
                        )
                    try:
                        row = runner.run(event_id, family, interval_h)
                        results.append(row)
                        if verbose:
                            status = "OK" if row.get("accepted") else f"FAIL({row.get('failure_reason', '?')})"
                            cc = "CC" if row.get("command_compliance") else "nc"
                            ic = "IC" if row.get("interval_compliance") else "ni"
                            print(f"{status} {cc} {ic}")
                    except Exception as exc:
                        if verbose:
                            print(f"ERROR: {exc}")
                        results.append({
                            "event_id": event_id,
                            "specified_release_family": family,
                            "operation_interval_h": interval_h,
                            "accepted": False,
                            "command_compliance": False,
                            "interval_compliance": False,
                            "failure_reason": str(exc),
                            "model_profile": model_profile,
                        })
    finally:
        runner.close()

    if results:
        df = pd.DataFrame(results)
        save_cols = [c for c in df.columns if c not in ("tool_call_sequence",)]
        df[save_cols].to_csv(output_dir / "results.csv", index=False)

    return results


def _write_summaries(results: list[dict[str, Any]], output_dir: Path) -> None:
    if not results:
        return
    df = pd.DataFrame(results)
    summary_dir = output_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    total = len(df)
    accepted = int(df["accepted"].sum()) if "accepted" in df.columns else 0
    cc = int(df["command_compliance"].sum()) if "command_compliance" in df.columns else 0
    ic = int(df["interval_compliance"].sum()) if "interval_compliance" in df.columns else 0
    hard_viol = int(df["hard_violation"].sum()) if "hard_violation" in df.columns else 0
    ds_viol = int(df["downstream_violation"].sum()) if "downstream_violation" in df.columns else 0
    tool_order_fail = int((~df["tool_order_valid"].astype(bool)).sum()) if "tool_order_valid" in df.columns else 0
    eval_ref_fail = int((~df["eval_ref_valid"].astype(bool)).sum()) if "eval_ref_valid" in df.columns else 0
    schema_fail = int((~df["schema_valid"].astype(bool)).sum()) if "schema_valid" in df.columns else 0

    metrics: dict[str, Any] = {
        "extension_type": "instruction_conditioned_static_llm",
        "model_profile": df["model_profile"].iloc[0] if "model_profile" in df.columns and total else None,
        "total_attempted": total,
        "accepted_count": accepted,
        "acceptance_rate": round(accepted / total, 4) if total else 0,
        "command_compliance_count": cc,
        "command_compliance_rate": round(cc / total, 4) if total else 0,
        "interval_compliance_count": ic,
        "interval_compliance_rate": round(ic / total, 4) if total else 0,
        "hard_violation_count": hard_viol,
        "downstream_violation_count": ds_viol,
        "tool_order_failure_count": tool_order_fail,
        "tool_order_validity_rate": round((total - tool_order_fail) / total, 4) if total else 0,
        "eval_ref_failure_count": eval_ref_fail,
        "eval_ref_validity_rate": round((total - eval_ref_fail) / total, 4) if total else 0,
        "schema_failure_count": schema_fail,
        "schema_validity_rate": round((total - schema_fail) / total, 4) if total else 0,
    }
    (summary_dir / "instruction_static_stage3_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # By release family
    if "specified_release_family" in df.columns:
        fam_agg = (
            df.groupby("specified_release_family")
            .agg(
                total=("event_id", "count"),
                accepted=("accepted", "sum"),
                command_compliance=("command_compliance", "sum"),
                interval_compliance=("interval_compliance", "sum"),
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
            )
            .reset_index()
        )
        int_agg.to_csv(summary_dir / "by_operation_interval.csv", index=False)

    # Failure taxonomy
    failed = df[~df["accepted"].astype(bool)]
    if "failure_reason" in failed.columns and not failed.empty:
        taxonomy = (
            failed.groupby("failure_reason")
            .agg(count=("event_id", "count"))
            .reset_index()
            .sort_values("count", ascending=False)
        )
        taxonomy.to_csv(summary_dir / "failure_taxonomy.csv", index=False)

    return metrics


def _run_comparison(
    stage2_dir: Path,
    stage3_dir: Path,
    verbose: bool,
) -> dict[str, Any]:
    """Compare Stage 3 LLM results against Stage 2 extension oracle."""
    import pandas as pd

    s2_csv = stage2_dir / "results.csv"
    s3_csv = stage3_dir / "results.csv"

    if not s2_csv.exists():
        print(f"Stage 2 oracle not found at {s2_csv} — skipping comparison.")
        return {}
    if not s3_csv.exists():
        print(f"Stage 3 results not found at {s3_csv} — skipping comparison.")
        return {}

    s2 = pd.read_csv(s2_csv)
    s3 = pd.read_csv(s3_csv)

    align_keys = ["event_id", "specified_release_family", "operation_interval_h"]
    for df in (s2, s3):
        for k in align_keys:
            if k not in df.columns:
                df[k] = ""

    def _make_key(df: pd.DataFrame) -> pd.Series:
        return df[align_keys].astype(str).agg("__".join, axis=1)

    s2_key = _make_key(s2)
    s3_key = _make_key(s3)
    s2_set, s3_set = set(s2_key), set(s3_key)
    matched = s2_set & s3_set
    missing = s2_set - s3_set
    extra = s3_set - s2_set

    # Merge for per-row comparison
    s2_idx = s2.copy(); s2_idx["_key"] = s2_key
    s3_idx = s3.copy(); s3_idx["_key"] = s3_key
    merged = s2_idx[s2_idx["_key"].isin(matched)].merge(
        s3_idx[s3_idx["_key"].isin(matched)],
        on="_key",
        suffixes=("_s2", "_s3"),
    )

    def _mismatch(col: str) -> int:
        c2 = f"{col}_s2" if f"{col}_s2" in merged.columns else col
        c3 = f"{col}_s3" if f"{col}_s3" in merged.columns else col
        if c2 in merged.columns and c3 in merged.columns:
            return int((merged[c2].astype(bool) != merged[c3].astype(bool)).sum())
        return 0

    cc_mismatch = _mismatch("command_compliance")
    ic_mismatch = _mismatch("interval_compliance")
    accepted_mismatch = _mismatch("accepted")

    # Failure taxonomy for Stage 3 rejections
    s3_failed = s3[~s3["accepted"].astype(bool)]
    taxonomy: dict[str, int] = {}
    if "failure_reason" in s3_failed.columns and not s3_failed.empty:
        counts = s3_failed["failure_reason"].value_counts()
        taxonomy = {str(k): int(v) for k, v in counts.items()}

    # Stage 3 acceptance stats
    s3_total = len(s3)
    s3_accepted = int(s3["accepted"].sum()) if "accepted" in s3.columns else 0
    s3_cc = int(s3["command_compliance"].sum()) if "command_compliance" in s3.columns else 0
    s3_ic = int(s3["interval_compliance"].sum()) if "interval_compliance" in s3.columns else 0

    passes_oracle = (
        # Subset-aware: only check rows that were actually attempted in Stage 3.
        # Non-attempted Stage 2 rows are NOT treated as missing.
        cc_mismatch == 0
        and ic_mismatch == 0
    )

    report = {
        "s2_total": len(s2),
        "s3_total": s3_total,
        "s3_subset_events": sorted(s3["event_id"].unique().tolist()) if "event_id" in s3.columns else [],
        "s3_accepted": s3_accepted,
        "s3_acceptance_rate": round(s3_accepted / s3_total, 4) if s3_total else 0,
        "s3_command_compliance_count": s3_cc,
        "s3_command_compliance_rate": round(s3_cc / s3_total, 4) if s3_total else 0,
        "s3_interval_compliance_count": s3_ic,
        "s3_interval_compliance_rate": round(s3_ic / s3_total, 4) if s3_total else 0,
        "matched_rows": len(matched),
        "missing_in_s3": len(missing),
        "extra_in_s3": len(extra),
        "accepted_mismatch": accepted_mismatch,
        "command_compliance_mismatches": cc_mismatch,
        "interval_compliance_mismatches": ic_mismatch,
        "passes_oracle": passes_oracle,
        "failure_taxonomy": taxonomy,
        "note": "Stage 3 instruction-static was evaluated on a representative subset. Full 492-row deterministic coverage is in Stage 1 and Stage 2.",
    }

    comparison_dir = stage3_dir / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    merged.to_csv(comparison_dir / "stage3_vs_stage2_instruction_static_comparison.csv", index=False)
    (comparison_dir / "instruction_static_comparison_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return report


def _write_markdown_summary(
    results: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
    output_dir: Path,
    model_profile: str,
) -> None:
    df = pd.DataFrame(results) if results else pd.DataFrame()
    total = len(df)
    accepted = int(df["accepted"].sum()) if "accepted" in df.columns and total else 0
    cc = int(df["command_compliance"].sum()) if "command_compliance" in df.columns and total else 0
    ic = int(df["interval_compliance"].sum()) if "interval_compliance" in df.columns and total else 0
    hard_viol = int(df["hard_violation"].sum()) if "hard_violation" in df.columns and total else 0
    ds_viol = int(df["downstream_violation"].sum()) if "downstream_violation" in df.columns and total else 0
    tool_order_fail = int((~df["tool_order_valid"].astype(bool)).sum()) if "tool_order_valid" in df.columns and total else 0
    eval_ref_fail = int((~df["eval_ref_valid"].astype(bool)).sum()) if "eval_ref_valid" in df.columns and total else 0
    schema_fail = int((~df["schema_valid"].astype(bool)).sum()) if "schema_valid" in df.columns and total else 0

    oracle_section = ""
    if comparison:
        oracle_pass = "PASS" if comparison.get("passes_oracle") else "FAIL"
        oracle_section = f"""
## Oracle Comparison (vs Stage 2 Extension)

| Metric | Value |
|--------|-------|
| Stage 2 rows | {comparison.get('s2_total', '-')} |
| Stage 3 rows | {comparison.get('s3_total', '-')} |
| Matched rows | {comparison.get('matched_rows', '-')} |
| Missing in Stage 3 | {comparison.get('missing_in_s3', '-')} |
| Command compliance mismatches | {comparison.get('command_compliance_mismatches', '-')} |
| Interval compliance mismatches | {comparison.get('interval_compliance_mismatches', '-')} |
| Oracle result | **{oracle_pass}** |
"""
        if comparison.get("failure_taxonomy"):
            oracle_section += "\n## Failure Taxonomy\n\n| Failure Reason | Count |\n|----------------|-------|\n"
            for reason, count in sorted(comparison["failure_taxonomy"].items(), key=lambda x: -x[1]):
                oracle_section += f"| {reason} | {count} |\n"

    import datetime
    subset_note = (
        "\n> **Note:** Stage 3 LLM evaluation was run on a representative 8-event subset "
        "(96 rows). Full 492-row deterministic coverage is in Stage 1 and Stage 2.\n"
    )
    md = f"""# Stage 3 Instruction-Conditioned Static Extension

Extension type: `instruction_conditioned_static_llm`
Model: `{model_profile}`
Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}
{subset_note}
## Results Summary

| Metric | Value |
|--------|-------|
| Total attempted | {total} |
| Accepted | {accepted} / {total} ({round(accepted/total*100, 1) if total else 0}%) |
| Command compliance | {cc} / {total} ({round(cc/total*100, 1) if total else 0}%) |
| Interval compliance | {ic} / {total} ({round(ic/total*100, 1) if total else 0}%) |
| Hard violations | {hard_viol} |
| Downstream violations | {ds_viol} |
| Tool-order failures | {tool_order_fail} |
| Eval-ref failures | {eval_ref_fail} |
| Schema failures | {schema_fail} |
{oracle_section}
## Acceptance Gate

```
accepted = tool_order_valid AND eval_ref_valid AND schema_valid
           AND NOT hard_violation AND NOT downstream_violation
           AND command_compliance AND interval_compliance
```
"""
    (output_dir / "STAGE3_INSTRUCTION_STATIC_SUMMARY.md").write_text(md.strip(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 3 instruction-conditioned static extension")
    parser.add_argument("--events", nargs="*", default=None)
    parser.add_argument("--events-file", default=None, dest="events_file",
                        help="Path to file with one event_id per line (pipe-separated format supported)")
    parser.add_argument("--release-family", nargs="*", default=None, dest="release_family")
    parser.add_argument("--operation-interval", nargs="*", type=int, default=None, dest="operation_interval")
    parser.add_argument("--model-profile", default=None, dest="model_profile")
    parser.add_argument("--output", default="experiments/results/stage3_instruction_static_mimo")
    parser.add_argument("--config", default="experiments/config/stage3_instruction_static.yml")
    parser.add_argument("--compare", action="store_true", default=False)
    parser.add_argument("--stage2-dir", default="experiments/results/stage2_instruction_static", dest="stage2_dir")
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    args = parser.parse_args(argv)

    config = _load_config(args.config)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    event_list_path = config.get("data", {}).get("event_list", "experiments/config/stage1_event_list_41.txt")
    all_events = _load_event_list(event_list_path)
    if args.events_file:
        events = _load_event_list(args.events_file)
    else:
        events = args.events or all_events
    families = args.release_family or config.get("release_families", RELEASE_FAMILIES)
    intervals = args.operation_interval or config.get("operation_intervals_h", [6, 12])
    model_profile = args.model_profile or config.get("model_profile", "mimo_v25")

    if args.compare and not (output_dir / "results.csv").exists():
        # Compare-only mode: no new runs
        comparison = _run_comparison(Path(args.stage2_dir), output_dir, args.verbose)
        if args.verbose and comparison:
            print(f"\nOracle comparison: passes_oracle={comparison.get('passes_oracle')}")
            print(f"  s3_accepted={comparison.get('s3_accepted')}/{comparison.get('s3_total')}")
            print(f"  command_compliance_rate={comparison.get('s3_command_compliance_rate')}")
            print(f"  interval_compliance_rate={comparison.get('s3_interval_compliance_rate')}")
            print(f"  missing_in_s3={comparison.get('missing_in_s3')}")
        return 0

    results = _run_matrix(config, events, families, intervals, output_dir, model_profile, args.verbose)
    metrics = _write_summaries(results, output_dir)

    comparison: dict[str, Any] | None = None
    if args.compare:
        comparison = _run_comparison(Path(args.stage2_dir), output_dir, args.verbose)
        if args.verbose and comparison:
            print(f"\nOracle comparison: passes_oracle={comparison.get('passes_oracle')}")
            print(f"  s3_accepted={comparison.get('s3_accepted')}/{comparison.get('s3_total')}")
            print(f"  command_compliance_rate={comparison.get('s3_command_compliance_rate')}")
            print(f"  interval_compliance_rate={comparison.get('s3_interval_compliance_rate')}")
            print(f"  missing_in_s3={comparison.get('missing_in_s3')}")

    _write_markdown_summary(results, comparison, output_dir, model_profile)

    if args.verbose:
        accepted = sum(1 for r in results if r.get("accepted"))
        cc = sum(1 for r in results if r.get("command_compliance"))
        ic = sum(1 for r in results if r.get("interval_compliance"))
        print(f"\nDone. {len(results)} rows, {accepted} accepted, {cc} CC, {ic} IC → {output_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
