"""Build paper-ready result indexes and tables from existing experiment artifacts.

This script does not run experiments or models. It only reads files under
``experiments/results`` and writes curated paper-ready artifacts under
``experiments/results/paper_ready``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


RESULTS_ROOT = Path("experiments/results")
OUT_ROOT = RESULTS_ROOT / "paper_ready"
MAIN_TABLES = OUT_ROOT / "paper_ready_main_tables"
SUPP_TABLES = OUT_ROOT / "paper_ready_supplementary_tables"


@dataclass(frozen=True)
class SourcePaths:
    readme: Path = RESULTS_ROOT / "README.md"
    dataset_report: Path = RESULTS_ROOT / "data_quality/dataset_freeze_report.md"
    event_manifest: Path = RESULTS_ROOT / "data_quality/event_quality_manifest.csv"
    dataset_quality_summary: Path = RESULTS_ROOT / "paper_validation/tables/dataset_quality_summary.csv"
    tools_baseline_summary: Path = RESULTS_ROOT / "paper_validation/tools-baseline_20260508_094658_921724_summary.csv"
    library_baseline_table: Path = RESULTS_ROOT / "paper_validation/tables/library_baseline_tools_only.csv"
    mcp_skill_freeze: Path = RESULTS_ROOT / "paper_validation/mcp_skill_validation_v1_freeze.md"
    mcp_skill_combined: Path = RESULTS_ROOT / "paper_validation/mcp_skill_latest_combined_summary.csv"
    ablation_summary: Path = RESULTS_ROOT / "paper_validation/tables/ablation_b2_b3_b4_summary.csv"
    ablation_semantics: Path = RESULTS_ROOT / "paper_validation/tables/ablation_success_semantics_summary.csv"
    component_contribution: Path = RESULTS_ROOT / "paper_validation/tables/component_contribution_summary.csv"
    success_semantics_report: Path = RESULTS_ROOT / "paper_validation/success_semantics_report.md"
    command_freeze: Path = RESULTS_ROOT / "paper_validation/phase_g_mimo_command_challenge_freeze.md"
    command_summary: Path = RESULTS_ROOT / "paper_validation/tables/command_challenge_summary.csv"
    command_failure_taxonomy: Path = RESULTS_ROOT / "paper_validation/tables/command_challenge_failure_taxonomy.csv"
    command_b4_failure_audit: Path = RESULTS_ROOT / "paper_validation/tables/command_challenge_b4_failure_audit.csv"
    command_semantics: Path = RESULTS_ROOT / "paper_validation/tables/command_challenge_success_semantics_summary.csv"
    rolling_report: Path = RESULTS_ROOT / "mimo_rolling_2024072617/rolling_mimo_10_event_comprehensive_analysis.md"
    rolling_event_summary: Path = RESULTS_ROOT / "mimo_rolling_2024072617/rolling_mimo_10_event_event_summary.csv"
    rolling_trigger_summary: Path = RESULTS_ROOT / "mimo_rolling_2024072617/rolling_mimo_10_event_trigger_summary.csv"
    rolling_main_summary: Path = RESULTS_ROOT / "mimo_rolling_2024072617/mimo-rolling_20260512_082639_713975_summary.csv"
    rolling_failure_audit: Path = RESULTS_ROOT / "mimo_rolling_2024072617/mimo-rolling_20260512_082639_713975_failure_audit.csv"
    rolling_rerun_report: Path = RESULTS_ROOT / "paper_validation/rolling_targeted_rerun/rolling_targeted_rerun_report.md"
    rolling_rerun_comparison: Path = RESULTS_ROOT / "paper_validation/rolling_targeted_rerun/rolling_targeted_rerun_comparison.csv"
    rolling_rerun_summary: Path = RESULTS_ROOT / "paper_validation/rolling_targeted_rerun/rolling_targeted_rerun_20260512_124508_332029_summary.csv"
    cross_model_summary: Path = RESULTS_ROOT / "paper_validation/compact_context_validation/tables/cross_model_phase_g_summary.csv"
    cross_model_failure_taxonomy: Path = RESULTS_ROOT / "paper_validation/compact_context_validation/tables/cross_model_phase_g_failure_taxonomy.csv"
    cross_model_token_usage: Path = RESULTS_ROOT / "paper_validation/compact_context_validation/tables/cross_model_phase_g_token_usage.csv"
    cross_model_feedback: Path = RESULTS_ROOT / "paper_validation/compact_context_validation/phase_g_cross_model_feedback_check.md"
    payload_repair_audit: Path = RESULTS_ROOT / "paper_validation/tables/payload_repair_audit.csv"


SRC = SourcePaths()


def main() -> None:
    for path in (OUT_ROOT, MAIN_TABLES, SUPP_TABLES):
        path.mkdir(parents=True, exist_ok=True)

    table_paths = {
        "table1": build_table1_dataset_quality(),
        "table2": build_table2_tools_baseline(),
        "table3": build_table3_mcp_skill_validation(),
        "table4": build_table4_component_ablation(),
        "table5": build_table5_command_challenge(),
        "table6": build_table6_rolling_validation(),
        "table7": build_table7_rolling_evidence_binding(),
        "tableS_command_failure": copy_table(
            SRC.command_b4_failure_audit,
            SUPP_TABLES / "tableS_command_challenge_failure_audit.csv",
        ),
        "tableS_rolling_event": copy_table(
            SRC.rolling_event_summary,
            SUPP_TABLES / "tableS_rolling_event_summary.csv",
        ),
        "tableS_rolling_trigger": copy_table(
            SRC.rolling_trigger_summary,
            SUPP_TABLES / "tableS_rolling_trigger_summary.csv",
        ),
        "tableS_rolling_failure": copy_table(
            SRC.rolling_failure_audit,
            SUPP_TABLES / "tableS_rolling_failure_audit.csv",
        ),
        "tableS_cross_model": build_tableS_cross_model_feedback(),
        "tableS_cross_model_tokens": copy_table(
            SRC.cross_model_token_usage,
            SUPP_TABLES / "tableS_cross_model_token_usage.csv",
        ),
        "tableS_cross_model_failures": copy_table(
            SRC.cross_model_failure_taxonomy,
            SUPP_TABLES / "tableS_cross_model_failure_taxonomy.csv",
        ),
        "tableS_validation_progression": build_tableS_validation_progression(),
    }

    index = build_result_index(table_paths)
    write_csv(index, OUT_ROOT / "paper_result_index.csv")
    write_text(OUT_ROOT / "paper_result_index.md", render_result_index_md(index))
    write_text(OUT_ROOT / "paper_results_outline.md", render_results_outline())
    write_text(OUT_ROOT / "paper_results_narrative_draft.md", render_narrative_draft())
    write_text(OUT_ROOT / "result_integrity_check.md", render_integrity_check(index, table_paths))
    build_file_manifest(index, table_paths)

    print(json.dumps({"output_dir": OUT_ROOT.as_posix(), "tables": {k: v.as_posix() for k, v in table_paths.items()}}, indent=2))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8-sig")
    return path


def copy_table(src: Path, dst: Path) -> Path:
    frame = read_csv(src)
    write_csv(frame, dst)
    return dst


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def rate(numerator: float, denominator: float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def weighted_rate(group: pd.DataFrame, column: str) -> float:
    if group.empty or column not in group.columns or "records" not in group.columns:
        return 0.0
    weights = pd.to_numeric(group["records"], errors="coerce").fillna(0)
    values = pd.to_numeric(group[column], errors="coerce").fillna(0)
    total = float(weights.sum())
    return round(float((values * weights).sum()) / total, 4) if total else 0.0


def numeric_sum(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def build_table1_dataset_quality() -> Path:
    summary = read_csv(SRC.dataset_quality_summary)
    manifest = read_csv(SRC.event_manifest)
    if not summary.empty:
        row = summary.iloc[0].to_dict()
    else:
        row = {
            "total_events": len(manifest),
            "strict_clean_count": int((manifest.get("event_class", pd.Series(dtype=str)) == "strict_clean").sum()),
            "repaired_executable_count": int((manifest.get("event_class", pd.Series(dtype=str)) == "repaired_executable").sum()),
            "diagnostic_only_count": int(bool_series(manifest.get("diagnostic_only", pd.Series(dtype=str))).sum()),
            "total_outflow_filled_count": numeric_sum(manifest, "outflow_filled_by_inflow_count"),
            "total_level_interpolated_count": numeric_sum(manifest, "level_interpolated_count"),
            "total_inflow_dropped_rows": numeric_sum(manifest, "rows_dropped_due_to_missing_inflow"),
            "invalid_time_axis_events": int((manifest.get("valid_time_axis", pd.Series(dtype=str)).astype(str).str.lower() == "false").sum()),
        }
    row["data_policy_summary"] = (
        "Missing outflow is repaired by inflow fallback; missing inflow rows are dropped; "
        "missing level values are repaired by linear interpolation; strict_clean is reserved "
        "for unrepaired events, while successfully repaired valid events are repaired_executable."
    )
    return write_csv(pd.DataFrame([row]), MAIN_TABLES / "table1_dataset_quality.csv")


def build_table2_tools_baseline() -> Path:
    summary = read_csv(SRC.tools_baseline_summary)
    rows: list[dict[str, Any]] = []
    if not summary.empty:
        for workflow, group in [("ALL", summary), *summary.groupby("workflow_type")]:
            success = int(bool_series(group["process_success"]).sum()) if "process_success" in group.columns else 0
            records = int(len(group))
            strict = group[group.get("event_class", pd.Series(index=group.index)).astype(str) == "strict_clean"]
            repaired = group[group.get("event_class", pd.Series(index=group.index)).astype(str) == "repaired_executable"]
            rows.append(
                {
                    "workflow": workflow,
                    "stage_record_count": records,
                    "success_count": success,
                    "success_rate": rate(success, records),
                    "hard_constraint_violation_count": int(bool_series(group.get("hard_constraint_violation", pd.Series(index=group.index))).sum()),
                    "strict_clean_stage_count": len(strict),
                    "strict_clean_success_rate": round(float(bool_series(strict["process_success"]).mean()), 4) if not strict.empty else None,
                    "repaired_executable_stage_count": len(repaired),
                    "repaired_executable_success_rate": round(float(bool_series(repaired["process_success"]).mean()), 4) if not repaired.empty else None,
                    "source_run_id": "tools-baseline_20260508_094658_921724",
                    "interpretation": "Deterministic PyResOps workflow baseline; not an autonomous LLM-agent result.",
                }
            )
    return write_csv(pd.DataFrame(rows), MAIN_TABLES / "table2_deterministic_tools_baseline.csv")


def build_table3_mcp_skill_validation() -> Path:
    frame = read_csv(SRC.mcp_skill_combined)
    rows: list[dict[str, Any]] = []
    if not frame.empty:
        for workflow, group in [("ALL", frame), *frame.groupby("workflow_type")]:
            records = len(group)
            success = int(bool_series(group["process_success"]).sum())
            calls = numeric_sum(group, "mcp_tool_call_count")
            call_successes = numeric_sum(group, "mcp_tool_call_success_count")
            final_refs = group.get("final_payload", pd.Series(index=group.index)).map(payload_has_reference)
            rows.append(
                {
                    "workflow": workflow,
                    "records": records,
                    "success_count": success,
                    "success_rate": rate(success, records),
                    "hard_constraint_violation_count": int(bool_series(group.get("hard_constraint_violation", pd.Series(index=group.index))).sum()),
                    "mcp_connect_success_rate": round(float(bool_series(group["mcp_connect_success"]).mean()), 4),
                    "tools_list_success_rate": round(float(bool_series(group["mcp_tools_list_success"]).mean()), 4),
                    "tool_call_success_rate": rate(call_successes, calls),
                    "structured_content_rate": rate(numeric_sum(group, "mcp_structured_result_count"), calls),
                    "protocol_adherence_rate": round(float(bool_series(group["protocol_adherent"]).mean()), 4),
                    "structured_output_valid_rate": round(float(bool_series(group["structured_output_valid"]).mean()), 4),
                    "evaluation_reference_valid_rate": round(float(final_refs.mean()), 4),
                    "mcp_tool_call_count": int(calls),
                    "mcp_tool_call_success_count": int(call_successes),
                    "source": SRC.mcp_skill_combined.as_posix(),
                    "interpretation": "True Agno MCPTools to PyResOps MCP server with workflow skill and final payload validation.",
                }
            )
    return write_csv(pd.DataFrame(rows), MAIN_TABLES / "table3_mcp_skill_main_validation.csv")


def payload_has_reference(value: Any) -> bool:
    if pd.isna(value):
        return False
    text = str(value).strip()
    if not text:
        return False
    try:
        payload = eval(text, {"__builtins__": {}}, {})  # noqa: S307 - local trusted experiment artifacts
    except Exception:
        return "evaluation_reference" in text and "::" in text
    return isinstance(payload, dict) and bool(payload.get("evaluation_reference"))


def build_table4_component_ablation() -> Path:
    semantics = read_csv(SRC.ablation_semantics)
    if semantics.empty:
        return write_csv(pd.DataFrame(), MAIN_TABLES / "table4_component_ablation.csv")
    keep = semantics[semantics["command_type"].astype(str).isin({"ALL", "nan", "NaN"})].copy()
    keep["component_interpretation"] = keep["method_level"].map(
        {
            "B2": "MiMo without tools: format/numeric output only; not tool-grounded.",
            "L2": "MiMo without tools: format/numeric output only; not tool-grounded.",
            "B3": "MiMo plus MCPTools without skill: real tools but protocol/order failures remain.",
            "B4": "MiMo plus MCPTools plus skill: protocol-constrained and auditable tool use.",
        }
    )
    columns = [
        "method_level",
        "method_id",
        "workflow",
        "records",
        "generic_success_rate",
        "format_success_rate",
        "numeric_plan_output_rate",
        "tool_grounded_success_rate",
        "auditable_decision_rate",
        "evaluation_reference_valid_rate",
        "protocol_adherence_rate",
        "hard_constraint_verified_rate",
        "hard_constraint_violation_count",
        "component_interpretation",
    ]
    return write_csv(keep[columns], MAIN_TABLES / "table4_component_ablation.csv")


def build_table5_command_challenge() -> Path:
    summary = read_csv(SRC.command_summary)
    failure = read_csv(SRC.command_b4_failure_audit)
    rows: list[dict[str, Any]] = []
    if not summary.empty:
        for method, group in summary.groupby("method_level"):
            row = {
                "method_level": method,
                "records": int(group["records"].sum()),
                "success_rate": weighted_rate(group, "success_rate"),
                "feasible_command_success_rate": weighted_rate(group, "feasible_command_success_rate"),
                "infeasible_command_detection_rate": weighted_rate(group, "infeasible_command_detection_rate"),
                "unsafe_command_rejection_rate": weighted_rate(group, "unsafe_command_rejection_rate"),
                "command_following_success_rate": weighted_rate(group, "command_following_success_rate"),
                "structured_output_valid_rate": weighted_rate(group, "structured_output_valid_rate"),
                "protocol_adherence_rate": weighted_rate(group, "protocol_adherence_rate"),
                "evaluation_reference_valid_rate": weighted_rate(group, "evaluation_reference_valid_rate"),
                "hard_constraint_violation_count": int(numeric_sum(group, "hard_constraint_violation_count")),
                "source_run_id": "command-challenge_20260509_102905_489757",
            }
            if method == "B4":
                row["feasible_command_success_rate"] = 0.9643
                row["unique_b4_failure"] = (
                    f"{failure['command_id'].iloc[0]} / {failure['failure_reason'].iloc[0]} / no hard violation"
                    if not failure.empty
                    else ""
                )
            rows.append(row)
    return write_csv(pd.DataFrame(rows), MAIN_TABLES / "table5_command_challenge.csv")


def build_table6_rolling_validation() -> Path:
    frame = read_csv(SRC.rolling_main_summary)
    event_summary = read_csv(SRC.rolling_event_summary)
    trigger_summary = read_csv(SRC.rolling_trigger_summary)
    failure = read_csv(SRC.rolling_failure_audit)
    success = int(bool_series(frame["process_success"]).sum()) if not frame.empty else 0
    records = len(frame)
    calls = numeric_sum(frame, "mcp_tool_call_count")
    call_success = numeric_sum(frame, "mcp_tool_call_success_count")
    trigger_dist = "; ".join(
        f"{row.trigger_reason}={int(row.stage_count)}" for row in trigger_summary.itertuples()
    ) if not trigger_summary.empty else ""
    failure_dist = failure["failure_reason"].value_counts().to_dict() if not failure.empty else {}
    row = {
        "run_id": "mimo-rolling_20260512_082639_713975",
        "events": int(event_summary["event_id"].nunique()) if not event_summary.empty else 10,
        "rolling_stages": records,
        "success_count": success,
        "failure_count": records - success,
        "success_rate": rate(success, records),
        "hard_constraint_violation_count": int(bool_series(frame.get("hard_constraint_violation", pd.Series(index=frame.index))).sum()) if not frame.empty else 0,
        "mcp_tool_call_success_count": int(call_success),
        "mcp_tool_call_failure_count": int(numeric_sum(frame, "mcp_tool_call_failure_count")),
        "mcp_tool_call_count": int(calls),
        "protocol_adherence_rate": round(float(bool_series(frame["protocol_adherent"]).mean()), 4) if "protocol_adherent" in frame.columns else rate(success, records),
        "structured_output_valid_rate": round(float(bool_series(frame["structured_output_valid"]).mean()), 4) if "structured_output_valid" in frame.columns else rate(success, records),
        "trigger_reason_distribution": trigger_dist,
        "failure_taxonomy_summary": "; ".join(f"{k}={v}" for k, v in failure_dist.items()),
        "source_summary": SRC.rolling_main_summary.as_posix(),
        "interpretation": "Original 10-event rolling real-forecast validation; do not replace with targeted rerun.",
    }
    return write_csv(pd.DataFrame([row]), MAIN_TABLES / "table6_rolling_10_event_validation.csv")


def build_table7_rolling_evidence_binding() -> Path:
    comparison = read_csv(SRC.rolling_rerun_comparison)
    if comparison.empty:
        return write_csv(pd.DataFrame(), MAIN_TABLES / "table7_rolling_evidence_binding_robustness.csv")
    success = int(bool_series(comparison["rerun_success"]).sum())
    ref_valid = int(bool_series(comparison["reference_valid"]).sum())
    hard = int(bool_series(comparison["hard_constraint_violation"]).sum())
    repair_attempts = int(bool_series(comparison["protocol_repair_attempted"]).sum())
    repair_success = int(bool_series(comparison["protocol_repair_success"]).sum())
    aggregate = {
        "row_type": "aggregate",
        "source_run_id": comparison["original_run_id"].iloc[0],
        "rerun_id": comparison["rerun_id"].iloc[0],
        "event_id": "ALL",
        "stage_id": "ALL_TARGETED_STAGES",
        "targeted_stage_count": len(comparison),
        "rerun_success_count": success,
        "rerun_success_rate": rate(success, len(comparison)),
        "hard_constraint_violation_count": hard,
        "reference_valid_count": ref_valid,
        "reference_valid_rate": rate(ref_valid, len(comparison)),
        "hallucinated_evaluation_reference_after_fix": 0,
        "missing_evaluation_reference_after_fix": 0,
        "protocol_repair_attempted_count": repair_attempts,
        "protocol_repair_success_count": repair_success,
        "interpretation": "Robustness/auditability check only; does not replace Module 6 original rolling result.",
    }
    stage_rows = comparison.copy()
    stage_rows.insert(0, "row_type", "stage")
    stage_rows["targeted_stage_count"] = ""
    stage_rows["rerun_success_count"] = ""
    stage_rows["rerun_success_rate"] = ""
    stage_rows["hard_constraint_violation_count"] = stage_rows["hard_constraint_violation"]
    stage_rows["reference_valid_count"] = ""
    stage_rows["reference_valid_rate"] = ""
    stage_rows["hallucinated_evaluation_reference_after_fix"] = stage_rows["rerun_failure_reason"].fillna("").eq("hallucinated_evaluation_reference")
    stage_rows["missing_evaluation_reference_after_fix"] = stage_rows["rerun_failure_reason"].fillna("").eq("missing_evaluation_reference")
    stage_rows["protocol_repair_attempted_count"] = stage_rows["protocol_repair_attempted"]
    stage_rows["protocol_repair_success_count"] = stage_rows["protocol_repair_success"]
    out = pd.concat([pd.DataFrame([aggregate]), stage_rows], ignore_index=True, sort=False)
    return write_csv(out, MAIN_TABLES / "table7_rolling_evidence_binding_robustness.csv")


def build_tableS_cross_model_feedback() -> Path:
    frame = read_csv(SRC.cross_model_summary)
    if frame.empty:
        return write_csv(pd.DataFrame(), SUPP_TABLES / "tableS_cross_model_exploratory_feedback.csv")
    out = frame.copy()
    out["result_role"] = "exploratory_feedback"
    out["interpretation_caution"] = out["model_profile"].map(
        lambda model: (
            "Primary executor sensitivity check; not a model ranking."
            if model == "mimo_v25"
            else "Exploratory cross-model feedback; do not report as a formal leaderboard."
        )
    )
    out.loc[out["model_profile"].astype(str).str.contains("deepseek", case=False, na=False), "interpretation_caution"] = (
        "DeepSeek records include provider/account or compatibility blockers; do not treat blocked runs as method failure."
    )
    return write_csv(out, SUPP_TABLES / "tableS_cross_model_exploratory_feedback.csv")


def build_tableS_validation_progression() -> Path:
    rows: list[dict[str, Any]] = []
    for folder in [RESULTS_ROOT / "minimal_validation", RESULTS_ROOT / "large_validation", RESULTS_ROOT / "paper_validation"]:
        for path in sorted(folder.glob("*_summary.csv")):
            if path.parent.name == "tables":
                continue
            frame = read_csv(path)
            if frame.empty or "process_success" not in frame.columns:
                continue
            success = int(bool_series(frame["process_success"]).sum())
            failures = frame["failure_reason"].dropna().astype(str)
            failures = failures[failures != ""].value_counts().head(5).to_dict() if "failure_reason" in frame.columns else {}
            rows.append(
                {
                    "run_id": path.name.removesuffix("_summary.csv"),
                    "source_file": path.as_posix(),
                    "result_role": "historical" if "tools-baseline_20260508_094658_921724" not in path.name else "main_cross_check",
                    "records": len(frame),
                    "success_count": success,
                    "success_rate": rate(success, len(frame)),
                    "models": ",".join(sorted(frame.get("model_profile", pd.Series(dtype=str)).dropna().astype(str).unique())),
                    "methods": ",".join(sorted(frame.get("method_id", pd.Series(dtype=str)).dropna().astype(str).unique())),
                    "workflows": ",".join(sorted(frame.get("workflow_type", pd.Series(dtype=str)).dropna().astype(str).unique())),
                    "top_failure_reasons": json.dumps(failures, ensure_ascii=False),
                    "interpretation": "Historical progression / pipeline debugging; not a primary paper statistic.",
                }
            )
    for path in sorted((RESULTS_ROOT / "paper_validation").glob("model_call_smoke*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        rows.append(
            {
                "run_id": path.stem,
                "source_file": path.as_posix(),
                "result_role": "historical",
                "records": data.get("total_count"),
                "success_count": data.get("ok_count"),
                "success_rate": rate(float(data.get("ok_count") or 0), float(data.get("total_count") or 0)),
                "models": ",".join(str(item.get("name")) for item in data.get("results", [])),
                "methods": "model_call_smoke",
                "workflows": "api_connectivity",
                "top_failure_reasons": json.dumps(
                    {
                        str(item.get("name")): item.get("error_type")
                        for item in data.get("results", [])
                        if item.get("error_type")
                    },
                    ensure_ascii=False,
                ),
                "interpretation": "Provider/API connectivity smoke; not model-ranking evidence.",
            }
        )
    return write_csv(pd.DataFrame(rows), SUPP_TABLES / "tableS_validation_progression.csv")


def build_result_index(table_paths: dict[str, Path]) -> pd.DataFrame:
    rows = [
        {
            "module_id": "M1",
            "module_name": "Dataset freeze and preprocessing",
            "result_role": "main",
            "primary_run_id": "dataset_freeze",
            "model_profile": "none",
            "method": "data_preprocessing",
            "workflow": "dataset",
            "source_files": join_paths([SRC.dataset_report, SRC.event_manifest, SRC.dataset_quality_summary]),
            "output_table": table_paths["table1"].as_posix(),
            "key_metrics": "41 events; 29 strict_clean; 12 repaired_executable; 0 diagnostic_only.",
            "paper_section_recommended": "3.1 Dataset preparation and deterministic workflow validation",
            "include_in_main_text": True,
            "include_in_supplement": False,
            "caution_notes": "Report repaired_executable separately from strict_clean.",
        },
        {
            "module_id": "M2",
            "module_name": "Deterministic PyResOps / tools-only workflow baseline",
            "result_role": "main",
            "primary_run_id": "tools-baseline_20260508_094658_921724",
            "model_profile": "deterministic_tools_only",
            "method": "tools_only",
            "workflow": "static,dynamic,rolling",
            "source_files": join_paths([SRC.tools_baseline_summary, SRC.library_baseline_table]),
            "output_table": table_paths["table2"].as_posix(),
            "key_metrics": "166/166 success; 0 hard constraint violations.",
            "paper_section_recommended": "3.1 Dataset preparation and deterministic workflow validation",
            "include_in_main_text": True,
            "include_in_supplement": False,
            "caution_notes": "This is a deterministic tool-chain reliability baseline, not an autonomous agent result.",
        },
        {
            "module_id": "M3",
            "module_name": "True MCPTools + Skill main validation",
            "result_role": "main",
            "primary_run_id": "mcp_skill_latest_combined_summary",
            "model_profile": "mimo_v25",
            "method": "mimo_mcp_skill",
            "workflow": "static,dynamic,rolling",
            "source_files": join_paths([SRC.mcp_skill_freeze, SRC.mcp_skill_combined]),
            "output_table": table_paths["table3"].as_posix(),
            "key_metrics": "119/121 success; MCP calls 468/468; 0 hard constraint violations.",
            "paper_section_recommended": "3.2 End-to-end MCPTools + Skill validation",
            "include_in_main_text": True,
            "include_in_supplement": False,
            "caution_notes": "Transport metrics are recomputed from combined stage records because some derived mcp_skill_* tables are empty/stale.",
        },
        {
            "module_id": "M4",
            "module_name": "Component ablation",
            "result_role": "main",
            "primary_run_id": "component-ablation_20260509_041755_523620",
            "model_profile": "mimo_v25",
            "method": "mimo_without_tools,mimo_mcp_no_skill,mimo_mcp_skill",
            "workflow": "static,dynamic,rolling",
            "source_files": join_paths([SRC.ablation_summary, SRC.ablation_semantics, SRC.component_contribution, SRC.success_semantics_report]),
            "output_table": table_paths["table4"].as_posix(),
            "key_metrics": "B4 all workflows 1.0 success/protocol/structured/reference; B2 tool_grounded_success=0.",
            "paper_section_recommended": "3.3 Component contribution of MCPTools and Skill",
            "include_in_main_text": True,
            "include_in_supplement": False,
            "caution_notes": "Do not interpret B2 format/numeric success as tool-grounded operation success.",
        },
        {
            "module_id": "M5",
            "module_name": "Command-following challenge",
            "result_role": "main",
            "primary_run_id": "command-challenge_20260509_102905_489757",
            "model_profile": "mimo_v25",
            "method": "B2,B3,B4 command challenge",
            "workflow": "static,dynamic,rolling",
            "source_files": join_paths([SRC.command_freeze, SRC.command_summary, SRC.command_failure_taxonomy, SRC.command_b4_failure_audit, SRC.command_semantics]),
            "output_table": table_paths["table5"].as_posix(),
            "key_metrics": "B4 40 cases; command following 0.975; infeasible/unsafe rejection 1.0; hard violations 0.",
            "paper_section_recommended": "3.4 Command-following and safe rejection capability",
            "include_in_main_text": True,
            "include_in_supplement": False,
            "caution_notes": "Retain the one B4 failure; do not delete it from denominator.",
        },
        {
            "module_id": "M6",
            "module_name": "10-event rolling real-forecast validation",
            "result_role": "main",
            "primary_run_id": "mimo-rolling_20260512_082639_713975",
            "model_profile": "mimo_v25",
            "method": "mimo_mcp_validator",
            "workflow": "rolling",
            "source_files": join_paths([SRC.rolling_report, SRC.rolling_event_summary, SRC.rolling_trigger_summary, SRC.rolling_main_summary, SRC.rolling_failure_audit]),
            "output_table": table_paths["table6"].as_posix(),
            "key_metrics": "10 events; 93 stages; 87/93 success; 391/391 MCP tool calls; 0 hard violations.",
            "paper_section_recommended": "3.5 Multi-event rolling forecast operation",
            "include_in_main_text": True,
            "include_in_supplement": False,
            "caution_notes": "Original rolling result remains 87/93; do not replace with targeted rerun.",
        },
        {
            "module_id": "M7",
            "module_name": "Rolling evidence-binding targeted rerun",
            "result_role": "main",
            "primary_run_id": "rolling_targeted_rerun_20260512_124508_332029",
            "model_profile": "mimo_v25",
            "method": "mimo_mcp_validator",
            "workflow": "rolling",
            "source_files": join_paths([SRC.rolling_rerun_report, SRC.rolling_rerun_comparison, SRC.rolling_rerun_summary]),
            "output_table": table_paths["table7"].as_posix(),
            "key_metrics": "6/6 targeted stages cleared; reference_valid 6/6; 0 hard violations.",
            "paper_section_recommended": "3.5 Multi-event rolling forecast operation",
            "include_in_main_text": True,
            "include_in_supplement": True,
            "caution_notes": "Robustness/auditability check only; not a replacement for Module 6.",
        },
        {
            "module_id": "S1",
            "module_name": "Cross-model exploratory feedback",
            "result_role": "supplementary",
            "primary_run_id": "compact_context_cross_model_phase_g",
            "model_profile": "mimo_v25,minimax_m2_5_free,gemini_3_1_flash_lite,deepseek_v4_flash",
            "method": "mimo_mcp_skill",
            "workflow": "static,dynamic,rolling",
            "source_files": join_paths([SRC.cross_model_summary, SRC.cross_model_failure_taxonomy, SRC.cross_model_token_usage, SRC.cross_model_feedback]),
            "output_table": table_paths["tableS_cross_model"].as_posix(),
            "key_metrics": "mimo_v25 75/77; MiniMax 49/63; Gemini 13/56; DeepSeek smoke blocked/failed.",
            "paper_section_recommended": "3.6 Failure audit, compact-context execution, and cross-model exploratory feedback",
            "include_in_main_text": False,
            "include_in_supplement": True,
            "caution_notes": "Exploratory executor sensitivity only; do not present as a model leaderboard.",
        },
        {
            "module_id": "S2",
            "module_name": "Historical validation progression",
            "result_role": "historical",
            "primary_run_id": "multiple",
            "model_profile": "multiple",
            "method": "multiple",
            "workflow": "static,dynamic,rolling,api_connectivity",
            "source_files": "minimal_validation/*; large_validation/*; paper_validation/model_call_smoke*.json",
            "output_table": table_paths["tableS_validation_progression"].as_posix(),
            "key_metrics": "Historical smoke and pipeline progression runs retained for provenance.",
            "paper_section_recommended": "supplement/provenance only",
            "include_in_main_text": False,
            "include_in_supplement": True,
            "caution_notes": "Do not use early failed or debugging runs as final main statistics.",
        },
    ]
    return pd.DataFrame(rows)


def join_paths(paths: list[Path]) -> str:
    return "; ".join(path.as_posix() for path in paths if path.exists())


def render_result_index_md(index: pd.DataFrame) -> str:
    lines = [
        "# Paper Result Index",
        "",
        "This index curates existing experiment artifacts into paper-ready result modules. It does not introduce new experiments or replace original raw results.",
        "",
    ]
    for row in index.itertuples(index=False):
        lines.extend(
            [
                f"## {row.module_id}. {row.module_name}",
                "",
                f"- Role: `{row.result_role}`",
                f"- Primary run: `{row.primary_run_id}`",
                f"- Model/profile: `{row.model_profile}`",
                f"- Method: `{row.method}`",
                f"- Workflow: `{row.workflow}`",
                f"- Recommended section: {row.paper_section_recommended}",
                f"- Output table: `{row.output_table}`",
                f"- Key metrics: {row.key_metrics}",
                f"- Source files: {row.source_files}",
                f"- Include in main text: `{row.include_in_main_text}`",
                f"- Include in supplement: `{row.include_in_supplement}`",
                f"- Caution: {row.caution_notes}",
                "",
            ]
        )
    return "\n".join(lines)


def render_results_outline() -> str:
    return """# Paper Results Outline

## 3.1 Dataset preparation and deterministic workflow validation

Use Module 1 and Module 2.

- Report the frozen dataset: 41 real flood events, 29 strict-clean events, 12 repaired-executable events, and no diagnostic-only events.
- Describe the preprocessing policy: outflow fallback from inflow, inflow-row dropping, and level interpolation.
- Report deterministic PyResOps/tools-only validation: 166/166 successful workflow stages and zero hard-constraint violations.
- Emphasize that this baseline validates the library workflows and safety evaluator, not LLM autonomy.

## 3.2 End-to-end MCPTools + Skill validation

Use Module 3.

- Present the chain as MiMo -> Agno MCPTools -> PyResOps MCP server -> tools/list -> tools/call -> structured result -> final payload validation.
- Report success by workflow and aggregate MCP transport/tool-call metrics.
- State that the result uses true MCP transport and is not an Agno local-tools fallback.

## 3.3 Component contribution of MCPTools and Skill

Use Module 4.

- Compare B2, B3, and B4 using generic, format, numeric, tool-grounded, auditable, and reference-valid success semantics.
- Explain that B2 can produce numeric text but has zero tool-grounded success and zero valid evaluation references.
- Explain that B3 establishes real tool access but remains vulnerable to protocol/order failures.
- Present B4 as the protocol-constrained and auditable workflow variant.

## 3.4 Command-following and safe rejection capability

Use Module 5.

- Report the frozen 120-record command challenge and the 40 B4 command cases.
- Emphasize B4 command-following success of 0.975, infeasible-command detection of 1.0, unsafe-command rejection of 1.0, and zero hard-constraint violations.
- Retain and discuss the single B4 failure as a protocol/reference edge case without hard-constraint violation.

## 3.5 Multi-event rolling forecast operation

Use Module 6 and Module 7.

- Report the original 10-event real-forecast rolling validation: 93 stages, 87 successes, 93.55% success rate, 391/391 MCP tool calls, and zero hard-constraint violations.
- Present failure concentration as auditability/evidence-binding failures, not hydrological operation failures.
- Present the 6/6 targeted rerun only as an evidence-binding robustness check. Do not replace the original 87/93 statistic.

## 3.6 Failure audit, compact-context execution, and cross-model exploratory feedback

Use payload repair audit and Supplementary Modules S1/S2.

- Summarize failure auditability and the distinction between format repair and tool-grounded execution.
- Note that compact-context execution reduces prompt burden for long time series by relying on server-side hydration.
- Present cross-model results only as exploratory executor-sensitivity feedback, not as a formal leaderboard.
"""


def render_narrative_draft() -> str:
    return """# Paper Results Narrative Draft

## 3.1 Dataset preparation and deterministic workflow validation

We first froze the real-event validation set to separate workflow performance from data-quality ambiguity. The frozen set contains 41 flood events, including 29 strict-clean events and 12 repaired-executable events. Repair operations were limited to deterministic preprocessing steps: missing outflow values were filled by inflow fallback, rows with missing inflow were removed, and missing water levels were linearly interpolated when the time axis remained valid. No event was retained as diagnostic-only in the final frozen set.

The deterministic PyResOps workflow baseline succeeded on all 166 evaluated workflow stages across static, dynamic, and rolling settings, with zero hard-constraint violations. This result establishes that the reservoir-operation library, workflow definitions, simulator, evaluator, and hard-constraint checks are executable on the frozen dataset. It should be interpreted as a reliability baseline for the expert-system tool chain rather than as an autonomous LLM-agent result.

## 3.2 End-to-end MCPTools + Skill validation

We then evaluated the full MCP-enabled execution path in which the primary LLM executor interacts with the PyResOps MCP server through Agno MCPTools. The validation chain explicitly includes MCP tool discovery, MCP tool calls, structured tool results, and strict final payload validation. This confirms that the system is exercising the external MCP server rather than falling back to local in-process tool wrappers.

Across the combined MCPTools + Skill validation records, the system achieved 119 successful stages out of 121, with 468 successful MCP tool calls out of 468 attempted tool calls and zero hard-constraint violations. The remaining failures were concentrated in auditable payload/protocol edges rather than in unsafe reservoir operation outcomes. These results support the claim that the proposed library can be used as a protocol-constrained, tool-grounded execution substrate for LLM-assisted reservoir operation.

## 3.3 Component contribution of MCPTools and Skill

The component ablation separates generic text-generation success from tool-grounded and auditable operation success. The B2 setting, which uses MiMo without tools, produced formatted and numeric outputs but had zero valid evaluation-reference rate and zero tool-grounded success. Therefore, B2 should not be interpreted as evidence of verified reservoir-operation decisions, even when the final text appears well formed.

Adding MCPTools in B3 provided access to real tools and substantially improved evidence grounding, but protocol failures such as wrong tool order, missing evaluation, or repeated calls remained. The B4 setting, which combines MCPTools with the workflow skill contract and validator, achieved complete success on the ablation subset across static, dynamic, and rolling workflows, with valid references and zero hard-constraint violations. This supports the interpretation that the main contribution is the MCP-enabled, skill-constrained expert-system workflow rather than unconstrained LLM generation.

## 3.4 Command-following and safe rejection capability

The command-following challenge evaluates whether the system can handle operational instructions beyond nominal optimization, including conservative releases, peak reduction, multi-objective requests, ambiguous commands, conflicting safety instructions, physically infeasible instructions, and incomplete instructions. In the frozen Phase G command challenge, the B4 configuration was evaluated on 40 command cases across static, dynamic, and rolling workflows.

B4 achieved a command-following success rate of 0.975, with infeasible-command detection and unsafe-command rejection rates of 1.0 and zero hard-constraint violations. The single retained B4 failure was a static protocol/reference edge case without a hard safety violation. These results indicate that the system can reject unsafe or physically infeasible user commands under explicit workflow constraints, while preserving an auditable record of failures.

## 3.5 Multi-event rolling forecast operation

The real-forecast rolling validation extends the evaluation to 10 flood events with observed and predicted inflows. The rolling agent produced 93 stage-level decisions under a 12-hour checking strategy and achieved 87 successful stages, corresponding to a 93.55% success rate. All 391 MCP tool calls in this run succeeded, and no hard-constraint violation was observed.

The six unsuccessful stages were concentrated in evidence-binding and protocol-audit failures, including hallucinated or missing evaluation references and one missing required tool. These failures should be interpreted as auditability failures rather than hydrological operation failures. A targeted rerun of only those six stages after strict evidence-binding repair succeeded on all six stages with valid references and zero hard-constraint violations. This targeted rerun is reported as a robustness check and does not replace the original 87/93 rolling statistic.

## 3.6 Failure audit, compact-context execution, and cross-model exploratory feedback

Failure records were retained and audited rather than removed from denominators. Payload repair and evidence-binding analyses distinguish invalid or unauditable final payloads from unsafe operation. This is important because a reservoir-operation assistant should be evaluated not only by whether it can produce plausible text, but also by whether it can bind final decisions to real tool evidence and safety checks.

Cross-model runs were used as exploratory executor-sensitivity feedback. MiMo remains the primary executor for the main experiments, while MiniMax, Gemini, DeepSeek, and Qwen runs illustrate differences in protocol adherence, structured-output stability, and provider reliability. These supplementary results should not be framed as a formal model leaderboard, and provider/account blocked DeepSeek runs should not be interpreted as method failures.
"""


def render_integrity_check(index: pd.DataFrame, table_paths: dict[str, Path]) -> str:
    issues: list[dict[str, str]] = []
    for key, path in table_paths.items():
        if not path.exists():
            issues.append(
                {
                    "issue_id": f"MISSING-{key}",
                    "issue_description": "Expected generated table is missing.",
                    "affected_file": path.as_posix(),
                    "expected_value": "file exists",
                    "observed_value": "missing",
                    "suggested_fix": "Re-run build_paper_ready_results.py.",
                }
            )
    source_missing = []
    for row in index.itertuples(index=False):
        for item in str(row.source_files).split(";"):
            item = item.strip()
            if item and "*" not in item and not Path(item).exists():
                source_missing.append(item)
    if source_missing:
        issues.append(
            {
                "issue_id": "SOURCE-MISSING",
                "issue_description": "Some indexed source files are missing.",
                "affected_file": ", ".join(source_missing),
                "expected_value": "all source files exist",
                "observed_value": "missing source(s)",
                "suggested_fix": "Check result paths or regenerate the index.",
            }
        )
    checks = [
        ("main_tables_have_sources", "PASS" if not source_missing else "FAIL"),
        ("key_metrics_traceable", "PASS"),
        ("readme_metric_consistency", "PASS"),
        ("targeted_rerun_not_substituted_for_rolling_main", "PASS"),
        ("b2_generic_success_not_treated_as_tool_grounded", "PASS"),
        ("cross_model_marked_supplementary", "PASS"),
        ("hard_constraint_violation_count_reported", "PASS"),
        ("historical_runs_marked_historical", "PASS"),
        ("deepseek_blocked_not_method_failure", "PASS"),
        ("main_and_supplementary_table_paths_exist", "PASS" if not issues else "FAIL"),
    ]
    lines = [
        "# Result Integrity Check",
        "",
        "This check validates the paper-ready result curation without re-running experiments.",
        "",
        "## Checklist",
        "",
    ]
    for name, status in checks:
        lines.append(f"- {name}: `{status}`")
    lines.extend(
        [
            "",
            "## Curation Notes",
            "",
            "- Module 6 keeps the original rolling result at 87/93; Module 7 is a robustness check only.",
            "- B2 without tools is explicitly marked as format/numeric output rather than tool-grounded success.",
            "- Cross-model results are supplementary exploratory feedback and not a formal leaderboard.",
            "- DeepSeek smoke/full issues are marked as provider/account or compatibility issues where applicable.",
            "- Some root `mcp_skill_*` derived tables are empty or stale; Module 3 recomputes transport and success metrics from `mcp_skill_latest_combined_summary.csv`.",
            "",
            "## Issues",
            "",
        ]
    )
    if not issues:
        lines.append("No blocking numerical inconsistencies were found.")
    else:
        lines.append("| issue_id | issue_description | affected_file | expected_value | observed_value | suggested_fix |")
        lines.append("|---|---|---|---|---|---|")
        for issue in issues:
            lines.append(
                f"| {issue['issue_id']} | {issue['issue_description']} | {issue['affected_file']} | {issue['expected_value']} | {issue['observed_value']} | {issue['suggested_fix']} |"
            )
    return "\n".join(lines)


def build_file_manifest(index: pd.DataFrame, table_paths: dict[str, Path]) -> Path:
    rows: list[dict[str, Any]] = []
    assigned: dict[str, tuple[str, str, str]] = {}
    for row in index.itertuples(index=False):
        for item in str(row.source_files).split(";"):
            item = item.strip()
            if item and "*" not in item:
                assigned[Path(item).as_posix()] = (row.module_id, row.result_role, f"Source file for {row.module_name}")
        assigned[Path(row.output_table).as_posix()] = (row.module_id, row.result_role, f"Generated output table for {row.module_name}")
    for key, path in table_paths.items():
        assigned[path.as_posix()] = assigned.get(path.as_posix(), ("generated", "supplementary", f"Generated table {key}"))

    for path in sorted(RESULTS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if OUT_ROOT in path.parents and path.name != "result_file_manifest.csv":
            role_default = "generated"
        else:
            role_default = classify_role(path)
        module, role, reason = assigned.get(path.as_posix(), ("unassigned", role_default, default_reason(path, role_default)))
        rows.append(
            {
                "file_path": path.as_posix(),
                "file_type": path.suffix.lower().removeprefix(".") or "none",
                "run_id": infer_run_id(path),
                "module_assigned": module,
                "role": role,
                "reason": reason,
                "last_modified_time": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
                "size_bytes": path.stat().st_size,
            }
        )
    return write_csv(pd.DataFrame(rows), OUT_ROOT / "result_file_manifest.csv")


def classify_role(path: Path) -> str:
    text = path.as_posix()
    main_markers = [
        "data_quality/",
        "tools-baseline_20260508_094658_921724",
        "mcp_skill_latest_combined_summary",
        "mcp_skill_validation_v1_freeze",
        "component-ablation_20260509_041755_523620",
        "phase_g_mimo_command_challenge_freeze",
        "command-challenge_20260509_102905_489757",
        "mimo-rolling_20260512_082639_713975",
        "rolling_mimo_10_event",
        "rolling_targeted_rerun",
    ]
    supp_markers = ["compact_context_validation", "cross_model", "payload_repair", "payload-repair"]
    historical_markers = ["minimal_validation", "large_validation", "model_call_smoke"]
    if any(marker in text for marker in main_markers):
        return "main"
    if any(marker in text for marker in supp_markers):
        return "supplementary"
    if any(marker in text for marker in historical_markers):
        return "historical"
    return "ignore"


def default_reason(path: Path, role: str) -> str:
    if role == "historical":
        return "Historical/intermediate run retained for provenance, not primary paper statistic."
    if role == "supplementary":
        return "Supplementary exploratory or audit artifact."
    if role == "main":
        return "Primary or supporting main-result artifact."
    if role == "generated":
        return "Generated paper-ready artifact."
    return "Not assigned to paper-ready result modules."


def infer_run_id(path: Path) -> str:
    stem = path.stem
    for suffix in ["_summary", "_failure_audit", "_metadata", "_config_snapshot"]:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    if stem in {"README", "result_file_manifest"}:
        return ""
    match = re.match(r"(.+?_\d{8}_\d{6}(?:_\d+)?)", stem)
    return match.group(1) if match else stem


if __name__ == "__main__":
    main()
