"""Stage 2 output reporting: CSVs, comparison JSON, and STAGE2_SUMMARY.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def generate_stage2_outputs(
    static_metrics: list[dict[str, Any]],
    dynamic_metrics: list[dict[str, Any]],
    rolling_metrics: list[dict[str, Any]],
    output_dir: str | Path,
) -> None:
    out = Path(output_dir)

    if static_metrics:
        d = out / "static"
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(static_metrics).to_csv(d / "all_events_metrics.csv", index=False)

    if dynamic_metrics:
        d = out / "dynamic"
        d.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(dynamic_metrics)
        df.to_csv(d / "stage_results.csv", index=False)
        retain_cols = ["event_id", "workflow_stage", "action", "trigger_type", "terminal_deviation"]
        df[[c for c in retain_cols if c in df.columns]].to_csv(
            d / "retain_replan_log.csv", index=False
        )

    if rolling_metrics:
        d = out / "rolling"
        d.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(rolling_metrics)
        df.to_csv(d / "stage_results.csv", index=False)
        trigger_cols = ["event_id", "workflow_stage", "trigger_type", "action", "max_level", "terminal_deviation"]
        df[[c for c in trigger_cols if c in df.columns]].to_csv(
            d / "trigger_log.csv", index=False
        )

    all_metrics = static_metrics + dynamic_metrics + rolling_metrics
    if not all_metrics:
        return

    summary_dir = out / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    df_all = pd.DataFrame(all_metrics)

    stats: dict[str, Any] = {
        "total_runs": len(all_metrics),
        "static_runs": len(static_metrics),
        "dynamic_runs": len(dynamic_metrics),
        "rolling_runs": len(rolling_metrics),
        "accepted_count": int(df_all["accepted"].sum()) if "accepted" in df_all.columns else None,
        "hard_violation_count": int(df_all["hard_violation"].sum()) if "hard_violation" in df_all.columns else None,
        "downstream_violation_count": int(df_all["downstream_violation"].sum()) if "downstream_violation" in df_all.columns else None,
        "mean_terminal_deviation": round(float(df_all["terminal_deviation"].mean()), 3) if "terminal_deviation" in df_all.columns else None,
        "mean_peak_reduction_rate": round(float(df_all["peak_reduction_rate"].mean()), 4) if "peak_reduction_rate" in df_all.columns else None,
    }
    (summary_dir / "stage2_metrics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def generate_comparison_report(
    comparison: dict[str, Any],
    output_dir: str | Path,
) -> None:
    out = Path(output_dir) / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison_report.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    rows = []
    for wf, info in comparison.get("workflow_summary", {}).items():
        rows.append({"workflow": wf, **info})
    if rows:
        pd.DataFrame(rows).to_csv(out / "workflow_summary.csv", index=False)


def _load_metrics_from_disk(output_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Read Stage 2 CSVs from disk when in-memory lists are empty."""
    def _read(path: Path) -> list[dict]:
        return pd.read_csv(path).to_dict("records") if path.exists() else []

    static = _read(output_dir / "static" / "all_events_metrics.csv")
    dynamic = _read(output_dir / "dynamic" / "stage_results.csv")
    rolling = _read(output_dir / "rolling" / "stage_results.csv")
    return static, dynamic, rolling


def generate_stage2_summary(
    static_metrics: list[dict[str, Any]],
    dynamic_metrics: list[dict[str, Any]],
    rolling_metrics: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
    output_dir: str | Path,
) -> None:
    out = Path(output_dir)

    # If called with --compare only (no --workflow), metrics lists are empty.
    # Fall back to reading the CSVs already on disk.
    if not static_metrics and not dynamic_metrics and not rolling_metrics:
        static_metrics, dynamic_metrics, rolling_metrics = _load_metrics_from_disk(out)

    all_metrics = static_metrics + dynamic_metrics + rolling_metrics
    total = len(all_metrics)

    accepted = sum(1 for r in all_metrics if r.get("accepted"))
    hard_viol = sum(1 for r in all_metrics if r.get("hard_violation"))
    ds_viol = sum(1 for r in all_metrics if r.get("downstream_violation"))

    oracle_section = ""
    if comparison:
        passes = comparison.get("passes_oracle", False)
        oracle_section = f"""
## Stage 1 Oracle Comparison

| Metric | Value |
|--------|-------|
| Stage 1 total rows | {comparison.get('s1_total', 'N/A')} |
| Stage 2 total rows | {comparison.get('s2_total', 'N/A')} |
| Matched rows | {comparison.get('matched_rows', 'N/A')} |
| Missing in Stage 2 | {comparison.get('missing_in_s2', 'N/A')} |
| Extra in Stage 2 | {comparison.get('extra_in_s2', 'N/A')} |
| `accepted` mismatches | {comparison.get('accepted_mismatch', 'N/A')} |
| `max_level` tolerance failures (±0.5 m) | {comparison.get('max_level_failures', 'N/A')} |
| `terminal_deviation` tolerance failures (±0.5 m) | {comparison.get('terminal_deviation_failures', 'N/A')} |
| `peak_reduction_rate` tolerance failures (±0.05) | {comparison.get('peak_reduction_failures', 'N/A')} |

**Oracle contract: {"PASS ✓" if passes else "FAIL ✗"}**
"""

    wf_rows = ""
    for wf, info in (comparison or {}).get("workflow_summary", {}).items():
        wf_rows += f"| {wf} | {info.get('s1_rows', '-')} | {info.get('s2_rows', '-')} |\n"

    md = f"""# Stage 2 Summary — Deterministic Workflow Replication

## Purpose

Stage 2 validates that the **workflow abstraction layer** (prepare → optimize → simulate →
evaluate → validate) reproduces Stage 1 results exactly. Stage 1 calls `OptimizationService`
directly; Stage 2 routes through `StaticWorkflow`, `DynamicWorkflow`, and `RollingWorkflow`
classes that wrap the same optimization kernel.

No LLM, no MCP, no agent layer is involved in Stage 2.

## How Stage 2 Differs from Stage 1

| Aspect | Stage 1 | Stage 2 |
|--------|---------|---------|
| Execution model | Direct service calls in `Stage1Runner` | Workflow classes with explicit step methods |
| Workflow abstraction | None | `prepare → optimize → simulate → evaluate → validate` |
| LLM / MCP | No | No |
| Optimization kernel | `OptimizationService` | Same `OptimizationService` |
| Result schema | `extract_unified_metrics()` | Same + `result_id`, `config_hash` |

## Workflow Coverage

| Workflow | Events | Stage 2 Rows |
|----------|--------|-------------|
| static | 41 | {len(static_metrics)} |
| dynamic | 10 | {len(dynamic_metrics)} |
| rolling | 10 | {len(rolling_metrics)} |
| **total** | | **{total}** |

## Result Statistics

| Metric | Value |
|--------|-------|
| Total rows | {total} |
| Accepted | {accepted} / {total} |
| Hard violations | {hard_viol} |
| Downstream violations | {ds_viol} |
{oracle_section}
## Workflow Summary (Stage 1 vs Stage 2 row counts)

| Workflow | Stage 1 rows | Stage 2 rows |
|----------|-------------|-------------|
{wf_rows}
## Discrepancy Taxonomy

If `passes_oracle` is True, no discrepancies exist. Any failures would fall into:

- **Row count mismatch** — different checkpoint or trigger counts (non-determinism in data loading)
- **Accepted mismatch** — optimizer feasibility changed (should not happen with identical kernel)
- **Tolerance failure** — floating-point drift beyond ±0.5 m / ±0.05 (should not happen)

## Alignment Key Note

Row matching uses `(event_id, workflow_stage)` as the join key. `scenario_type` is excluded
because Stage 1 derives it from `workflow_stage.split("_")[0]` (so dynamic rows get `"T0"`,
`"T1"`, etc.) while Stage 2 uses canonical names (`"dynamic"`, `"rolling"`). The
`workflow_stage` labels (`static`, `T0`–`T4`, `rolling_Xh`) are unique across all workflow
types and serve as stable identifiers.
"""

    (out / "STAGE2_SUMMARY.md").write_text(md.strip(), encoding="utf-8")
