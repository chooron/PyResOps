"""Stage 3 dynamic command-intervention CLI.

Usage:
    # Smoke test (1 event x 4 command types x 2 checkpoints = 8 rows)
    python -m experiments.run_stage3_dynamic_command_intervention --events 2024061623 --model-profile mimo_v25 --output experiments/results/stage3_dynamic_command_mimo_smoke

    # Full run (5 events x 4 command types x 2 checkpoints = 40 rows)
    python -m experiments.run_stage3_dynamic_command_intervention --model-profile mimo_v25 --output experiments/results/stage3_dynamic_command_mimo

    # Compare against Stage 2 oracle
    python -m experiments.run_stage3_dynamic_command_intervention --compare --stage2-dir experiments/results/stage2_dynamic_command_intervention --output experiments/results/stage3_dynamic_command_mimo
"""

from __future__ import annotations

import argparse
import datetime
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

from experiments.stage1.dynamic_command_intervention import (
    SELECTED_EVENTS,
    COMMAND_TYPES,
    CHECKPOINT_LABELS,
)
from experiments.stage3.dynamic_command_runner import DynamicCommandLlmRunner


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _run_matrix(
    config: dict,
    events: list[str],
    command_types: list[str],
    checkpoints: list[str],
    output_dir: Path,
    model_profile: str,
    verbose: bool,
) -> list[dict[str, Any]]:
    data_root = config.get("data", {}).get("root", "data")
    traces_dir = str(output_dir / "traces")

    runner = DynamicCommandLlmRunner(
        model_profile=model_profile,
        config_path=config.get("llm_config_path"),
        paper_config=config,
        data_root=data_root,
        traces_dir=traces_dir,
    )

    total = len(events) * len(command_types) * len(checkpoints)
    if verbose:
        print(f"Stage 3 dynamic command-intervention:")
        print(f"  Model: {model_profile}")
        print(f"  Events: {len(events)}, Commands: {len(command_types)}, Checkpoints: {checkpoints}")
        print(f"  Total runs: {total}")

    results: list[dict[str, Any]] = []
    run_num = 0
    try:
        for event_id in events:
            for checkpoint_id in checkpoints:
                for command_type in command_types:
                    run_num += 1
                    if verbose:
                        print(
                            f"  [{run_num}/{total}] {event_id} | {checkpoint_id} | {command_type} ...",
                            end=" ",
                            flush=True,
                        )
                    try:
                        row = runner.run(event_id, checkpoint_id, command_type)
                        results.append(row)
                        if verbose:
                            status = "OK" if row.get("accepted") else f"FAIL({row.get('failure_reason', '?')})"
                            chs = "CHS" if row.get("command_handling_success") else "nch"
                            fes = "FES" if row.get("feasible_execution_success") else "nfe"
                            print(f"{status} {chs} {fes}")
                    except Exception as exc:
                        if verbose:
                            print(f"ERROR: {exc}")
                        results.append({
                            "event_id": event_id,
                            "checkpoint_id": checkpoint_id,
                            "command_type": command_type,
                            "accepted": False,
                            "command_handling_success": False,
                            "feasible_execution_success": False,
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


def _write_summaries(results: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    if not results:
        return {}
    df = pd.DataFrame(results)
    summary_dir = output_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    total = len(df)

    def _count(col: str) -> int:
        return int(df[col].sum()) if col in df.columns else 0

    def _neg_count(col: str) -> int:
        return int((~df[col].astype(bool)).sum()) if col in df.columns else 0

    accepted = _count("accepted")
    chs = _count("command_handling_success")
    fes = _count("feasible_execution_success")
    hard_viol = _count("hard_violation")
    ds_viol = _count("downstream_violation")
    tool_order_fail = _neg_count("tool_order_valid")
    eval_ref_fail = _neg_count("eval_ref_valid")
    schema_fail = _neg_count("schema_valid")

    metrics: dict[str, Any] = {
        "extension_type": "dynamic_command_intervention_llm",
        "model_profile": df["model_profile"].iloc[0] if "model_profile" in df.columns and total else None,
        "total_attempted": total,
        "accepted_count": accepted,
        "acceptance_rate": round(accepted / total, 4) if total else 0,
        "command_handling_success_count": chs,
        "command_handling_success_rate": round(chs / total, 4) if total else 0,
        "feasible_execution_success_count": fes,
        "feasible_execution_success_rate": round(fes / total, 4) if total else 0,
        "hard_violation_count": hard_viol,
        "downstream_violation_count": ds_viol,
        "tool_order_failure_count": tool_order_fail,
        "tool_order_validity_rate": round((total - tool_order_fail) / total, 4) if total else 0,
        "eval_ref_failure_count": eval_ref_fail,
        "eval_ref_validity_rate": round((total - eval_ref_fail) / total, 4) if total else 0,
        "schema_failure_count": schema_fail,
        "schema_validity_rate": round((total - schema_fail) / total, 4) if total else 0,
    }
    (summary_dir / "dynamic_command_stage3_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # By command type
    if "command_type" in df.columns:
        cmd_agg = (
            df.groupby("command_type")
            .agg(
                total=("event_id", "count"),
                accepted=("accepted", "sum"),
                command_handling_success=("command_handling_success", "sum"),
                feasible_execution_success=("feasible_execution_success", "sum"),
            )
            .reset_index()
        )
        cmd_agg.to_csv(summary_dir / "by_command_type.csv", index=False)

    # By checkpoint
    if "checkpoint_id" in df.columns:
        cp_agg = (
            df.groupby("checkpoint_id")
            .agg(
                total=("event_id", "count"),
                accepted=("accepted", "sum"),
                command_handling_success=("command_handling_success", "sum"),
            )
            .reset_index()
        )
        cp_agg.to_csv(summary_dir / "by_checkpoint.csv", index=False)

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
    s2_csv = stage2_dir / "results.csv"
    s3_csv = stage3_dir / "results.csv"

    if not s2_csv.exists():
        if verbose:
            print(f"Stage 2 oracle not found at {s2_csv} — skipping comparison.")
        return {}
    if not s3_csv.exists():
        if verbose:
            print(f"Stage 3 results not found at {s3_csv} — skipping comparison.")
        return {}

    s2 = pd.read_csv(s2_csv)
    s3 = pd.read_csv(s3_csv)

    align_keys = ["event_id", "checkpoint_id", "command_type"]
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

    s2_idx = s2.copy(); s2_idx["_key"] = s2_key
    s3_idx = s3.copy(); s3_idx["_key"] = s3_key
    merged = s2_idx[s2_idx["_key"].isin(matched)].merge(
        s3_idx[s3_idx["_key"].isin(matched)],
        on="_key",
        suffixes=("_s2", "_s3"),
    )

    def _bool_mismatch(col: str) -> int:
        c2 = f"{col}_s2" if f"{col}_s2" in merged.columns else col
        c3 = f"{col}_s3" if f"{col}_s3" in merged.columns else col
        if c2 in merged.columns and c3 in merged.columns:
            return int((merged[c2].astype(bool) != merged[c3].astype(bool)).sum())
        return 0

    def _tol_failures(col: str, tol: float) -> int:
        c2 = f"{col}_s2" if f"{col}_s2" in merged.columns else col
        c3 = f"{col}_s3" if f"{col}_s3" in merged.columns else col
        if c2 in merged.columns and c3 in merged.columns:
            diff = abs(
                pd.to_numeric(merged[c2], errors="coerce")
                - pd.to_numeric(merged[c3], errors="coerce")
            )
            return int((diff > tol).sum())
        return 0

    accepted_mismatch = _bool_mismatch("accepted")
    chs_mismatch = _bool_mismatch("command_handling_success")
    fes_mismatch = _bool_mismatch("feasible_execution_success")
    feasibility_mismatch = 0
    if "command_feasibility_s2" in merged.columns and "command_feasibility_s3" in merged.columns:
        feasibility_mismatch = int(
            (merged["command_feasibility_s2"].astype(str) != merged["command_feasibility_s3"].astype(str)).sum()
        )
    outcome_mismatch = 0
    if "command_outcome_s2" in merged.columns and "command_outcome_s3" in merged.columns:
        outcome_mismatch = int(
            (merged["command_outcome_s2"].astype(str) != merged["command_outcome_s3"].astype(str)).sum()
        )

    max_level_failures = _tol_failures("max_level", 0.5)
    terminal_dev_failures = _tol_failures("terminal_deviation", 0.5)
    attenuation_failures = _tol_failures("inflow_peak_attenuation_rate", 0.05)

    s3_failed = s3[~s3["accepted"].astype(bool)] if "accepted" in s3.columns else pd.DataFrame()
    taxonomy: dict[str, int] = {}
    if "failure_reason" in s3_failed.columns and not s3_failed.empty:
        counts = s3_failed["failure_reason"].value_counts()
        taxonomy = {str(k): int(v) for k, v in counts.items()}

    s3_total = len(s3)
    s3_accepted = int(s3["accepted"].sum()) if "accepted" in s3.columns else 0
    s3_chs = int(s3["command_handling_success"].sum()) if "command_handling_success" in s3.columns else 0
    s3_fes = int(s3["feasible_execution_success"].sum()) if "feasible_execution_success" in s3.columns else 0

    passes_oracle = (
        chs_mismatch == 0
        and fes_mismatch == 0
        and feasibility_mismatch == 0
    )

    report = {
        "s2_total": len(s2),
        "s3_total": s3_total,
        "s3_accepted": s3_accepted,
        "s3_acceptance_rate": round(s3_accepted / s3_total, 4) if s3_total else 0,
        "s3_command_handling_success_count": s3_chs,
        "s3_command_handling_success_rate": round(s3_chs / s3_total, 4) if s3_total else 0,
        "s3_feasible_execution_success_count": s3_fes,
        "s3_feasible_execution_success_rate": round(s3_fes / s3_total, 4) if s3_total else 0,
        "matched_rows": len(matched),
        "missing_in_s3": len(missing),
        "extra_in_s3": len(extra),
        "accepted_mismatch": accepted_mismatch,
        "command_handling_success_mismatches": chs_mismatch,
        "feasible_execution_success_mismatches": fes_mismatch,
        "command_feasibility_mismatches": feasibility_mismatch,
        "command_outcome_mismatches": outcome_mismatch,
        "max_level_tolerance_failures": max_level_failures,
        "terminal_deviation_tolerance_failures": terminal_dev_failures,
        "attenuation_tolerance_failures": attenuation_failures,
        "passes_oracle": passes_oracle,
        "failure_taxonomy": taxonomy,
    }

    comparison_dir = stage3_dir / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    merged.to_csv(
        comparison_dir / "stage3_vs_stage2_dynamic_command_comparison.csv", index=False
    )
    (comparison_dir / "dynamic_command_comparison_report.json").write_text(
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

    def _c(col: str) -> int:
        return int(df[col].sum()) if col in df.columns and total else 0

    def _nc(col: str) -> int:
        return int((~df[col].astype(bool)).sum()) if col in df.columns and total else 0

    accepted = _c("accepted")
    chs = _c("command_handling_success")
    fes = _c("feasible_execution_success")
    hard_viol = _c("hard_violation")
    ds_viol = _c("downstream_violation")
    tool_order_fail = _nc("tool_order_valid")
    eval_ref_fail = _nc("eval_ref_valid")
    schema_fail = _nc("schema_valid")

    oracle_section = ""
    if comparison:
        oracle_pass = "PASS" if comparison.get("passes_oracle") else "FAIL"
        oracle_section = f"""
## Oracle Comparison (vs Stage 2)

| Metric | Value |
|--------|-------|
| Stage 2 rows | {comparison.get('s2_total', '-')} |
| Stage 3 rows | {comparison.get('s3_total', '-')} |
| Matched rows | {comparison.get('matched_rows', '-')} |
| Missing in Stage 3 | {comparison.get('missing_in_s3', '-')} |
| command_handling_success mismatches | {comparison.get('command_handling_success_mismatches', '-')} |
| feasible_execution_success mismatches | {comparison.get('feasible_execution_success_mismatches', '-')} |
| command_feasibility mismatches | {comparison.get('command_feasibility_mismatches', '-')} |
| max_level tolerance failures | {comparison.get('max_level_tolerance_failures', '-')} |
| terminal_deviation tolerance failures | {comparison.get('terminal_deviation_tolerance_failures', '-')} |
| Oracle result | **{oracle_pass}** |
"""
        if comparison.get("failure_taxonomy"):
            oracle_section += "\n## Failure Taxonomy\n\n| Failure Reason | Count |\n|----------------|-------|\n"
            for reason, count in sorted(comparison["failure_taxonomy"].items(), key=lambda x: -x[1]):
                oracle_section += f"| {reason} | {count} |\n"

    md = f"""# Stage 3 Dynamic Command-Intervention

Extension type: `dynamic_command_intervention_llm`
Model: `{model_profile}`
Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}

## Results Summary

| Metric | Value |
|--------|-------|
| Total attempted | {total} |
| Accepted | {accepted} / {total} ({round(accepted/total*100, 1) if total else 0}%) |
| command_handling_success | {chs} / {total} ({round(chs/total*100, 1) if total else 0}%) |
| feasible_execution_success | {fes} / {total} ({round(fes/total*100, 1) if total else 0}%) |
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
           AND command_handling_success
```
"""
    (output_dir / "STAGE3_DYNAMIC_COMMAND_SUMMARY.md").write_text(md.strip(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 3 dynamic command-intervention")
    parser.add_argument("--events", nargs="*", default=None)
    parser.add_argument("--command-types", nargs="*", default=None, dest="command_types")
    parser.add_argument("--checkpoints", nargs="*", default=None)
    parser.add_argument("--model-profile", default=None, dest="model_profile")
    parser.add_argument("--output", default="experiments/results/stage3_dynamic_command_mimo")
    parser.add_argument("--config", default="experiments/config/stage3_dynamic_command_intervention.yml")
    parser.add_argument("--compare", action="store_true", default=False)
    parser.add_argument("--stage2-dir", default="experiments/results/stage2_dynamic_command_intervention", dest="stage2_dir")
    parser.add_argument("--verbose", "-v", action="store_true", default=True)
    args = parser.parse_args(argv)

    config = _load_config(args.config)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    events = args.events or config.get("events", SELECTED_EVENTS)
    command_types = args.command_types or config.get("command_types", COMMAND_TYPES)
    checkpoints = args.checkpoints or config.get("checkpoints", CHECKPOINT_LABELS)
    model_profile = args.model_profile or config.get("model_profile", "mimo_v25")

    if args.compare and not (output_dir / "results.csv").exists():
        comparison = _run_comparison(Path(args.stage2_dir), output_dir, args.verbose)
        if args.verbose and comparison:
            print(f"\nOracle comparison: passes_oracle={comparison.get('passes_oracle')}")
            print(f"  s3_accepted={comparison.get('s3_accepted')}/{comparison.get('s3_total')}")
            print(f"  command_handling_success_rate={comparison.get('s3_command_handling_success_rate')}")
            print(f"  missing_in_s3={comparison.get('missing_in_s3')}")
        return 0

    results = _run_matrix(config, events, command_types, checkpoints, output_dir, model_profile, args.verbose)
    _write_summaries(results, output_dir)

    comparison: dict[str, Any] | None = None
    if args.compare:
        comparison = _run_comparison(Path(args.stage2_dir), output_dir, args.verbose)
        if args.verbose and comparison:
            print(f"\nOracle comparison: passes_oracle={comparison.get('passes_oracle')}")
            print(f"  s3_accepted={comparison.get('s3_accepted')}/{comparison.get('s3_total')}")
            print(f"  command_handling_success_rate={comparison.get('s3_command_handling_success_rate')}")
            print(f"  missing_in_s3={comparison.get('missing_in_s3')}")

    _write_markdown_summary(results, comparison, output_dir, model_profile)

    if args.verbose:
        accepted = sum(1 for r in results if r.get("accepted"))
        chs = sum(1 for r in results if r.get("command_handling_success"))
        fes = sum(1 for r in results if r.get("feasible_execution_success"))
        print(f"\nDone. {len(results)} rows, {accepted} accepted, {chs} CHS, {fes} FES → {output_dir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
