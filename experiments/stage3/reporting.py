"""Stage 3 output reporting: CSVs, comparison JSON, and STAGE3_SUMMARY.md."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def generate_stage3_outputs(
    static_metrics: list[dict[str, Any]],
    dynamic_metrics: list[dict[str, Any]],
    rolling_metrics: list[dict[str, Any]],
    output_dir: str | Path,
) -> None:
    out = Path(output_dir)

    if static_metrics:
        d = out / "static"
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(static_metrics).to_csv(d / "results.csv", index=False)

    if dynamic_metrics:
        d = out / "dynamic"
        d.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(dynamic_metrics)
        df.to_csv(d / "results.csv", index=False)
        retain_cols = ["event_id", "workflow_stage", "accepted", "failure_reason", "tool_order_valid", "eval_ref_valid"]
        df[[c for c in retain_cols if c in df.columns]].to_csv(d / "validation_log.csv", index=False)

    if rolling_metrics:
        d = out / "rolling"
        d.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(rolling_metrics)
        df.to_csv(d / "results.csv", index=False)
        trigger_cols = ["event_id", "workflow_stage", "accepted", "failure_reason", "tool_order_valid", "eval_ref_valid"]
        df[[c for c in trigger_cols if c in df.columns]].to_csv(d / "validation_log.csv", index=False)

    all_metrics = static_metrics + dynamic_metrics + rolling_metrics
    if not all_metrics:
        return

    summary_dir = out / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    df_all = pd.DataFrame(all_metrics)

    def _count(col: str) -> int:
        return int(df_all[col].sum()) if col in df_all.columns else 0

    def _mean(col: str, decimals: int = 3) -> float | None:
        if col in df_all.columns:
            return round(float(pd.to_numeric(df_all[col], errors="coerce").mean()), decimals)
        return None

    stats: dict[str, Any] = {
        "total_runs": len(all_metrics),
        "static_runs": len(static_metrics),
        "dynamic_runs": len(dynamic_metrics),
        "rolling_runs": len(rolling_metrics),
        "accepted_count": _count("accepted"),
        "rejected_count": len(all_metrics) - _count("accepted"),
        "tool_order_failures": int(df_all["failure_reason"].isin({"wrong_tool_order", "missing_required_tool"}).sum()) if "failure_reason" in df_all.columns else 0,
        "eval_ref_failures": int(df_all["failure_reason"].isin({"missing_eval_ref", "stale_eval_ref"}).sum()) if "failure_reason" in df_all.columns else 0,
        "schema_failures": int(df_all["failure_reason"].isin({"llm_output_parse_error", "schema_error", "invalid_final_payload"}).sum()) if "failure_reason" in df_all.columns else 0,
        "hard_violations": _count("hard_violation"),
        "downstream_violations": _count("downstream_violation"),
        "mean_terminal_deviation": _mean("terminal_deviation"),
        "mean_peak_reduction_rate": _mean("peak_reduction_rate", 4),
    }
    (summary_dir / "stage3_metrics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def generate_stage3_comparison(
    comparison: dict[str, Any],
    output_dir: str | Path,
) -> None:
    out = Path(output_dir) / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage3_vs_stage2_comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    rows = []
    for wf, info in comparison.get("workflow_summary", {}).items():
        rows.append({"workflow": wf, **info})
    if rows:
        pd.DataFrame(rows).to_csv(out / "workflow_summary.csv", index=False)

    taxonomy = comparison.get("failure_taxonomy", {})
    if taxonomy:
        pd.DataFrame(
            [{"failure_reason": k, "count": v} for k, v in taxonomy.items()]
        ).to_csv(out / "failure_taxonomy.csv", index=False)


def _load_metrics_from_disk(output_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    def _read(path: Path) -> list[dict]:
        return pd.read_csv(path).to_dict("records") if path.exists() else []

    static = _read(output_dir / "static" / "results.csv")
    dynamic = _read(output_dir / "dynamic" / "results.csv")
    rolling = _read(output_dir / "rolling" / "results.csv")
    return static, dynamic, rolling


def generate_stage3_summary(
    static_metrics: list[dict[str, Any]],
    dynamic_metrics: list[dict[str, Any]],
    rolling_metrics: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
    output_dir: str | Path,
    model_profile: str = "mimo_v25",
) -> None:
    out = Path(output_dir)

    if not static_metrics and not dynamic_metrics and not rolling_metrics:
        static_metrics, dynamic_metrics, rolling_metrics = _load_metrics_from_disk(out)

    all_metrics = static_metrics + dynamic_metrics + rolling_metrics
    total = len(all_metrics)

    accepted = sum(1 for r in all_metrics if r.get("accepted"))
    hard_viol = sum(1 for r in all_metrics if r.get("hard_violation"))
    ds_viol = sum(1 for r in all_metrics if r.get("downstream_violation"))
    # Use failure_reason as authoritative primary cause (flags cascade on every rejected row)
    _tool_order_reasons = {"wrong_tool_order", "missing_required_tool"}
    _eval_ref_reasons = {"missing_eval_ref", "stale_eval_ref"}
    _schema_reasons = {"llm_output_parse_error", "schema_error", "invalid_final_payload"}
    tool_order_fail = sum(1 for r in all_metrics if str(r.get("failure_reason") or "") in _tool_order_reasons)
    eval_ref_fail = sum(1 for r in all_metrics if str(r.get("failure_reason") or "") in _eval_ref_reasons)
    schema_fail = sum(1 for r in all_metrics if str(r.get("failure_reason") or "") in _schema_reasons)

    # Rolling two-tier breakdown
    rolling_section = ""
    rolling_llm = [r for r in rolling_metrics if r.get("llm_called", True) not in (False, "False")]
    rolling_retain = [r for r in rolling_metrics if r.get("llm_called", True) in (False, "False")]
    rolling_llm_accepted = sum(1 for r in rolling_llm if r.get("accepted"))
    rolling_retain_accepted = sum(1 for r in rolling_retain if r.get("accepted"))
    rolling_llm_fail_taxonomy: dict[str, int] = {}
    for r in rolling_llm:
        if not r.get("accepted"):
            reason = str(r.get("failure_reason") or "unknown")
            rolling_llm_fail_taxonomy[reason] = rolling_llm_fail_taxonomy.get(reason, 0) + 1

    rolling_section = ""
    if rolling_metrics:
        rolling_section = f"""
## Rolling Workflow Breakdown

| Category | Count |
|----------|-------|
| Total rolling checks | {len(rolling_metrics)} |
| LLM-called checks | {len(rolling_llm)} |
| Deterministic retain rows | {len(rolling_retain)} |
| Accepted LLM decisions | {rolling_llm_accepted} / {len(rolling_llm)} |
| Accepted retain rows | {rolling_retain_accepted} / {len(rolling_retain)} |
| Rolling events covered | {len(set(r.get('event_id') for r in rolling_metrics))} / 10 |
"""
        if rolling_llm_fail_taxonomy:
            rolling_section += "\n### Rolling LLM Failure Taxonomy\n\n| Failure Reason | Count |\n|----------------|-------|\n"
            for reason, count in sorted(rolling_llm_fail_taxonomy.items(), key=lambda x: -x[1]):
                rolling_section += f"| {reason} | {count} |\n"

    oracle_section = ""
    if comparison:
        passes = comparison.get("passes_oracle", False)
        oracle_section = f"""
## Stage 2 Oracle Comparison

| Metric | Value |
|--------|-------|
| Stage 2 total rows | {comparison.get('s2_total', 'N/A')} |
| Stage 3 total rows | {comparison.get('s3_total', 'N/A')} |
| Matched rows | {comparison.get('matched_rows', 'N/A')} |
| Missing in Stage 3 | {comparison.get('missing_in_s3', 'N/A')} |
| Extra in Stage 3 | {comparison.get('extra_in_s3', 'N/A')} |
| `max_level` tolerance failures (±0.5 m) | {comparison.get('max_level_failures', 'N/A')} |
| `terminal_deviation` tolerance failures (±0.5 m) | {comparison.get('terminal_deviation_failures', 'N/A')} |
| `peak_reduction_rate` tolerance failures (±0.05) | {comparison.get('peak_reduction_failures', 'N/A')} |

**Oracle contract: {"PASS ✓" if passes else "FAIL ✗"}**
"""

    wf_rows = ""
    for wf, info in (comparison or {}).get("workflow_summary", {}).items():
        wf_rows += f"| {wf} | {info.get('s2_rows', 'N/A')} | {info.get('s3_rows', 'N/A')} | {info.get('s3_accepted', 'N/A')} |\n"

    taxonomy_section = ""
    if comparison and comparison.get("failure_taxonomy"):
        taxonomy_section = "\n## Failure Taxonomy\n\n| Failure Reason | Count |\n|----------------|-------|\n"
        for reason, count in sorted(comparison["failure_taxonomy"].items(), key=lambda x: -x[1]):
            taxonomy_section += f"| {reason} | {count} |\n"

    md = f"""# Stage 3 Summary: LLM + MCP Tool-Use Evaluation

## Overview

Stage 3 evaluates whether an LLM can correctly execute reservoir operation workflows
through MCP tools, produce valid decision payloads, and pass fail-closed validation.

| Property | Value |
|----------|-------|
| Model profile | `{model_profile}` |
| Fail-closed gate | tool_order AND eval_ref AND schema AND NOT hard_violation AND NOT downstream_violation |
| Oracle | Stage 2 deterministic results |

## Workflow Coverage

| Workflow | Stage 2 Rows | Stage 3 Rows | Stage 3 Accepted |
|----------|-------------|-------------|-----------------|
{wf_rows}
## Validation Statistics

| Metric | Value |
|--------|-------|
| Total runs | {total} |
| Accepted (all gates pass) | {accepted} / {total} |
| Hard violations | {hard_viol} |
| Downstream violations | {ds_viol} |
| Tool-order failures | {tool_order_fail} |
| Eval-ref failures | {eval_ref_fail} |
| Schema / parse failures | {schema_fail} |
{rolling_section}{oracle_section}{taxonomy_section}
## Alignment Key Note

Row matching uses `(event_id, workflow_stage)` as the join key. Stage 3 `workflow_type`
values (`dynamic_replan`, `dynamic_retain`, `rolling_replan`, `rolling_retain`) differ from
Stage 2 canonical names (`dynamic`, `rolling`), so `workflow_stage` labels (`static`,
`T0`–`T4`, `rolling_Xh`) are used as stable identifiers.
"""

    (out / "STAGE3_SUMMARY.md").write_text(md.strip(), encoding="utf-8")
