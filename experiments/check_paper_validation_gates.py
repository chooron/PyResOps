"""Gate checks for paper-validation runs."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.paper_validation.command_challenge import (
    command_challenge_gate_metrics,
    deepseek_subset_gate_metrics,
)


def evaluate_gates(
    summary_path: str | Path,
    *,
    include_mcp_skill: bool = False,
    include_component_ablation: bool = False,
    include_command_challenge: bool = False,
    include_deepseek_subset: bool = False,
) -> dict[str, Any]:
    frame = _ensure_gate_columns(pd.read_csv(summary_path, encoding="utf-8-sig"))
    metrics = _summary_metrics(frame)
    failures: list[dict[str, Any]] = []

    include_phase_g_only = include_command_challenge or include_deepseek_subset
    if not include_phase_g_only:
        _check_gate(
            failures,
            "tools_only_success_rate",
            (metrics["tools_only_record_count"] == 0) or metrics["tools_only_success_rate"] == 1.0,
            metrics["tools_only_success_rate"],
            "Check tools baseline regressions.",
        )
        _check_gate(
            failures,
            "tools_only_hard_constraint_violation_count",
            (metrics["tools_only_record_count"] == 0)
            or metrics["tools_only_hard_constraint_violation_count"] == 0,
            metrics["tools_only_hard_constraint_violation_count"],
            "Inspect safety evaluation or reservoir spec mismatch.",
        )
        _check_gate(
            failures,
            "mimo_static_strict_clean_success_rate",
            (metrics["mimo_static_strict_clean_record_count"] == 0)
            or metrics["mimo_static_strict_clean_success_rate"] >= 0.95,
            metrics["mimo_static_strict_clean_success_rate"],
            "Review static prompt and protocol adherence.",
        )
        _check_gate(
            failures,
            "mimo_static_repaired_success_rate",
            (metrics["mimo_static_repaired_record_count"] == 0)
            or metrics["mimo_static_repaired_success_rate"] >= 0.95,
            metrics["mimo_static_repaired_success_rate"],
            "Review repaired-event handling in static prompt.",
        )
        _check_gate(
            failures,
            "mimo_dynamic_carry_over_evaluation_rate",
            (metrics["mimo_dynamic_record_count"] == 0)
            or metrics["mimo_dynamic_carry_over_evaluation_rate"] == 1.0,
            metrics["mimo_dynamic_carry_over_evaluation_rate"],
            "Carry-over evaluate-first protocol is violated.",
        )
        _check_gate(
            failures,
            "mimo_dynamic_protocol_adherence_rate",
            (metrics["mimo_dynamic_record_count"] == 0)
            or metrics["mimo_dynamic_protocol_adherence_rate"] >= 0.95,
            metrics["mimo_dynamic_protocol_adherence_rate"],
            "Review dynamic prompt and tool-chain taxonomy.",
        )
        _check_gate(
            failures,
            "mimo_rolling_real_success_rate",
            (metrics["mimo_rolling_real_record_count"] == 0)
            or metrics["mimo_rolling_real_success_rate"] == 1.0,
            metrics["mimo_rolling_real_success_rate"],
            "Review rolling real-forecast setup.",
        )
        _check_gate(
            failures,
            "rolling_stress_success_rate",
            (metrics["rolling_stress_record_count"] == 0)
            or metrics["rolling_stress_success_rate"] >= 0.90,
            metrics["rolling_stress_success_rate"],
            "Review forecast-error stress protocol or model robustness.",
        )
    if include_mcp_skill:
        _check_mcp_skill_gates(failures, metrics)
    if include_component_ablation:
        _check_component_ablation_gates(failures, metrics)
    if include_command_challenge:
        _check_command_challenge_gates(failures, metrics)
    if include_deepseek_subset:
        _check_deepseek_subset_gates(failures, metrics)

    status = "PASS" if not failures else "FAIL"
    return {
        "status": status,
        "failed_gate_names": [item["gate"] for item in failures],
        "failures": failures,
        "metrics": metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--include-mcp-skill", action="store_true")
    parser.add_argument("--include-component-ablation", action="store_true")
    parser.add_argument("--include-command-challenge", action="store_true")
    parser.add_argument("--include-deepseek-subset", action="store_true")
    args = parser.parse_args()

    summary_path = (
        _build_latest_phase_summary("deepseek-mcp-skill-subset")
        if args.include_deepseek_subset and args.latest and args.run_id is None
        else
        _build_latest_phase_summary("command-challenge")
        if args.include_command_challenge and args.latest and args.run_id is None
        else
        _build_latest_component_ablation_summary()
        if args.include_component_ablation and args.latest and args.run_id is None
        else
        _build_latest_mcp_combined_summary()
        if args.include_mcp_skill and args.latest and args.run_id is None
        else _resolve_summary_path(args.run_id, args.latest)
    )
    result = evaluate_gates(
        summary_path,
        include_mcp_skill=args.include_mcp_skill,
        include_component_ablation=args.include_component_ablation,
        include_command_challenge=args.include_command_challenge,
        include_deepseek_subset=args.include_deepseek_subset,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


def _resolve_summary_path(run_id: str | None, latest: bool) -> Path:
    root = Path("experiments/results/paper_validation")
    if run_id:
        candidate = root / f"{run_id}_summary.csv"
        if not candidate.exists():
            raise FileNotFoundError(f"Missing summary for run_id={run_id}: {candidate}")
        return candidate
    if latest:
        candidates = sorted(root.glob("*_summary.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidates:
            raise FileNotFoundError("No paper-validation summary files found")
        return candidates[0]
    raise ValueError("Provide --run-id or --latest")


def _build_latest_mcp_combined_summary() -> Path:
    from experiments.paper_validation.orchestrator import export_mcp_skill_tables

    root = Path("experiments/results/paper_validation")
    phases = [
        "mcp-skill-smoke",
        "mcp-skill-static",
        "mcp-skill-dynamic",
        "mcp-skill-rolling",
        "mcp-skill-rolling-stress",
    ]
    frames = []
    for phase in phases:
        candidates = sorted(root.glob(f"{phase}_*_summary.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidates:
            continue
        frames.append(pd.read_csv(candidates[0], encoding="utf-8-sig"))
    if not frames:
        raise FileNotFoundError("No mcp-skill summary files found")
    output = root / "mcp_skill_latest_combined_summary.csv"
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined.to_csv(output, index=False, encoding="utf-8-sig")
    export_mcp_skill_tables(combined, root / "tables")
    return output


def _build_latest_component_ablation_summary() -> Path:
    root = Path("experiments/results/paper_validation")
    candidates = sorted(root.glob("component-ablation_*_summary.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        candidates = sorted(
            root.glob("component-ablation-smoke_*_summary.csv"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    if not candidates:
        raise FileNotFoundError("No component-ablation summary files found")
    return candidates[0]


def _build_latest_phase_summary(phase: str) -> Path:
    root = Path("experiments/results/paper_validation")
    candidates = sorted(root.glob(f"{phase}_*_summary.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No {phase} summary files found")
    return candidates[0]


def _check_gate(failures: list[dict[str, Any]], gate: str, ok: bool, metric: Any, suggestion: str) -> None:
    if not ok:
        failures.append({"gate": gate, "metric": metric, "suggested_next_action": suggestion})


def _check_mcp_skill_gates(failures: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    _check_gate(
        failures,
        "mcp_skill_smoke",
        (metrics["mcp_skill_smoke_record_count"] == 0)
        or (
            metrics["mcp_skill_smoke_connect_success_rate"] == 1.0
            and metrics["mcp_skill_smoke_tools_list_success_rate"] == 1.0
            and metrics["mcp_skill_smoke_tool_call_success_count"] >= 1
            and metrics["mcp_skill_smoke_final_payload_valid_rate"] == 1.0
        ),
        {
            "connect_success_rate": metrics["mcp_skill_smoke_connect_success_rate"],
            "tools_list_success_rate": metrics["mcp_skill_smoke_tools_list_success_rate"],
            "tool_call_success_count": metrics["mcp_skill_smoke_tool_call_success_count"],
            "final_payload_valid_rate": metrics["mcp_skill_smoke_final_payload_valid_rate"],
        },
        "Check MCP server startup, tools/list, tools/call, and final payload parsing.",
    )


def _check_component_ablation_gates(failures: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    _check_gate(
        failures,
        "component_b2_records_and_classification",
        metrics["component_b2_record_count"] > 0
        and metrics["component_b2_unclassified_failure_count"] == 0,
        {
            "record_count": metrics["component_b2_record_count"],
            "unclassified_failure_count": metrics["component_b2_unclassified_failure_count"],
        },
        "Ensure B2 no-tools produces records and classified parser/validator outcomes.",
    )
    _check_gate(
        failures,
        "component_b3_mcp_transport",
        (metrics["component_b3_record_count"] == 0)
        or (
            metrics["component_b3_mcp_connect_success_rate"] >= 0.95
            and metrics["component_b3_mcp_tools_list_success_rate"] >= 0.95
            and metrics["component_b3_mcp_tool_call_success_rate"] >= 0.95
            and metrics["component_b3_hard_constraint_violation_count"] == 0
        ),
        {
            "record_count": metrics["component_b3_record_count"],
            "connect_success_rate": metrics["component_b3_mcp_connect_success_rate"],
            "tools_list_success_rate": metrics["component_b3_mcp_tools_list_success_rate"],
            "tool_call_success_rate": metrics["component_b3_mcp_tool_call_success_rate"],
            "hard_constraint_violation_count": metrics["component_b3_hard_constraint_violation_count"],
        },
        "Review B3 MCPTools no-skill transport and safety traces.",
    )
    _check_gate(
        failures,
        "component_b4_skill",
        (metrics["component_b4_record_count"] == 0)
        or (
            metrics["component_b4_success_rate"] >= 0.95
            and metrics["component_b4_hard_constraint_violation_count"] == 0
            and metrics["component_b4_protocol_adherence_rate"] >= 0.95
            and metrics["component_b4_structured_output_valid_rate"] >= 0.95
        ),
        {
            "record_count": metrics["component_b4_record_count"],
            "success_rate": metrics["component_b4_success_rate"],
            "hard_constraint_violation_count": metrics["component_b4_hard_constraint_violation_count"],
            "protocol_adherence_rate": metrics["component_b4_protocol_adherence_rate"],
            "structured_output_valid_rate": metrics["component_b4_structured_output_valid_rate"],
        },
        "Review B4 MCPTools+Skill subset traces.",
    )
    _check_gate(
        failures,
        "mcp_skill_static",
        (metrics["mcp_skill_static_record_count"] == 0)
        or (
            metrics["mcp_skill_static_strict_clean_success_rate"] >= 0.95
            and metrics["mcp_skill_static_repaired_success_rate"] >= 0.95
            and metrics["mcp_skill_static_hard_constraint_violation_count"] == 0
            and metrics["mcp_skill_static_tool_call_success_rate"] >= 0.95
            and metrics["mcp_skill_static_structured_output_valid_rate"] >= 0.95
            and metrics["mcp_skill_static_protocol_adherence_rate"] >= 0.95
        ),
        {
            "strict_clean_success_rate": metrics["mcp_skill_static_strict_clean_success_rate"],
            "repaired_success_rate": metrics["mcp_skill_static_repaired_success_rate"],
            "hard_constraint_violation_count": metrics["mcp_skill_static_hard_constraint_violation_count"],
            "tool_call_success_rate": metrics["mcp_skill_static_tool_call_success_rate"],
            "structured_output_valid_rate": metrics["mcp_skill_static_structured_output_valid_rate"],
            "protocol_adherence_rate": metrics["mcp_skill_static_protocol_adherence_rate"],
        },
        "Review static MCP skill protocol and transport trace.",
    )
    _check_gate(
        failures,
        "mcp_skill_dynamic",
        (metrics["mcp_skill_dynamic_record_count"] == 0)
        or (
            metrics["mcp_skill_dynamic_success_rate"] >= 0.95
            and metrics["mcp_skill_dynamic_hard_constraint_violation_count"] == 0
            and metrics["mcp_skill_dynamic_carry_over_evaluation_rate"] == 1.0
            and metrics["mcp_skill_dynamic_protocol_adherence_rate"] >= 0.95
            and metrics["mcp_skill_dynamic_tool_call_success_rate"] >= 0.95
            and metrics["mcp_skill_dynamic_structured_output_valid_rate"] >= 0.95
        ),
        {
            "success_rate": metrics["mcp_skill_dynamic_success_rate"],
            "carry_over_evaluation_rate": metrics["mcp_skill_dynamic_carry_over_evaluation_rate"],
            "protocol_adherence_rate": metrics["mcp_skill_dynamic_protocol_adherence_rate"],
        },
        "Review dynamic carry-over evaluate-first MCP protocol.",
    )
    _check_gate(
        failures,
        "mcp_skill_rolling",
        (metrics["mcp_skill_rolling_record_count"] == 0)
        or (
            metrics["mcp_skill_rolling_success_rate"] == 1.0
            and metrics["mcp_skill_rolling_hard_constraint_violation_count"] == 0
            and metrics["mcp_skill_rolling_trigger_reason_coverage_rate"] == 1.0
            and metrics["mcp_skill_rolling_tool_call_success_rate"] >= 0.95
            and metrics["mcp_skill_rolling_structured_output_valid_rate"] >= 0.95
        ),
        {
            "success_rate": metrics["mcp_skill_rolling_success_rate"],
            "trigger_reason_coverage_rate": metrics["mcp_skill_rolling_trigger_reason_coverage_rate"],
        },
        "Review rolling trigger context and MCP final payload.",
    )
    _check_gate(
        failures,
        "mcp_skill_rolling_stress",
        (metrics["mcp_skill_rolling_stress_record_count"] == 0)
        or (
            metrics["mcp_skill_rolling_stress_success_rate"] >= 0.90
            and metrics["mcp_skill_rolling_stress_hard_constraint_violation_count"] == 0
            and metrics["mcp_skill_rolling_stress_forecast_error_type_coverage_rate"] == 1.0
            and metrics["mcp_skill_rolling_stress_tool_call_success_rate"] >= 0.95
        ),
        {
            "success_rate": metrics["mcp_skill_rolling_stress_success_rate"],
            "forecast_error_type_coverage_rate": metrics["mcp_skill_rolling_stress_forecast_error_type_coverage_rate"],
        },
        "Review forecast-error stress MCP traces.",
    )


def _check_command_challenge_gates(failures: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    _check_gate(
        failures,
        "command_challenge_mimo_b4",
        (metrics["command_b4_record_count"] == 0)
        or (
            metrics["command_b4_hard_constraint_violation_count"] == 0
            and metrics["command_b4_structured_output_valid_rate"] >= 0.95
            and metrics["command_b4_protocol_adherence_rate"] >= 0.95
            and metrics["command_b4_infeasible_command_detection_rate"] >= 0.90
            and metrics["command_b4_unsafe_command_rejection_rate"] >= 0.90
        ),
        {
            "record_count": metrics["command_b4_record_count"],
            "hard_constraint_violation_count": metrics["command_b4_hard_constraint_violation_count"],
            "structured_output_valid_rate": metrics["command_b4_structured_output_valid_rate"],
            "protocol_adherence_rate": metrics["command_b4_protocol_adherence_rate"],
            "infeasible_command_detection_rate": metrics["command_b4_infeasible_command_detection_rate"],
            "unsafe_command_rejection_rate": metrics["command_b4_unsafe_command_rejection_rate"],
        },
        "Review B4 command skill coverage, infeasible-command handling, and evaluation references.",
    )
    _check_gate(
        failures,
        "command_challenge_b4_vs_b3",
        (metrics["command_b4_record_count"] == 0)
        or (
            metrics["command_b4_command_following_success_rate"]
            >= metrics["command_b3_command_following_success_rate"]
            and metrics["command_b4_evaluation_reference_valid_rate"]
            >= metrics["command_b3_evaluation_reference_valid_rate"]
        ),
        {
            "b4_command_following_success_rate": metrics["command_b4_command_following_success_rate"],
            "b3_command_following_success_rate": metrics["command_b3_command_following_success_rate"],
            "b4_evaluation_reference_valid_rate": metrics["command_b4_evaluation_reference_valid_rate"],
            "b3_evaluation_reference_valid_rate": metrics["command_b3_evaluation_reference_valid_rate"],
        },
        "Compare B4 command and evaluation-reference records against B3 without hiding B3 wins.",
    )
    _check_gate(
        failures,
        "command_challenge_b2_evaluation_reference",
        (metrics["command_b2_record_count"] == 0)
        or metrics["command_b2_evaluation_reference_valid_rate"] <= 0.20
        or metrics["command_b2_evaluation_reference_valid_rate"]
        < metrics["command_b4_evaluation_reference_valid_rate"],
        {
            "b2_evaluation_reference_valid_rate": metrics["command_b2_evaluation_reference_valid_rate"],
            "b4_evaluation_reference_valid_rate": metrics["command_b4_evaluation_reference_valid_rate"],
        },
        "Ensure B2 text-only references are not counted as tool-grounded evaluation evidence.",
    )


def _check_deepseek_subset_gates(failures: list[dict[str, Any]], metrics: dict[str, Any]) -> None:
    _check_gate(
        failures,
        "deepseek_subset",
        (metrics["deepseek_record_count"] == 0)
        or (
            metrics["deepseek_success_rate"] >= 0.90
            and metrics["deepseek_hard_constraint_violation_count"] == 0
            and metrics["deepseek_mcp_tool_call_success_rate"] >= 0.95
            and metrics["deepseek_structured_output_valid_rate"] >= 0.90
            and metrics["deepseek_protocol_adherence_rate"] >= 0.90
            and metrics["deepseek_command_unsafe_rejection_rate"] >= 0.80
            and metrics["deepseek_command_infeasible_detection_rate"] >= 0.80
        ),
        {
            "record_count": metrics["deepseek_record_count"],
            "success_rate": metrics["deepseek_success_rate"],
            "hard_constraint_violation_count": metrics["deepseek_hard_constraint_violation_count"],
            "mcp_tool_call_success_rate": metrics["deepseek_mcp_tool_call_success_rate"],
            "structured_output_valid_rate": metrics["deepseek_structured_output_valid_rate"],
            "protocol_adherence_rate": metrics["deepseek_protocol_adherence_rate"],
            "unsafe_command_rejection_rate": metrics["deepseek_command_unsafe_rejection_rate"],
            "infeasible_command_detection_rate": metrics["deepseek_command_infeasible_detection_rate"],
        },
        "Review DeepSeek MCPTools+Skill subset traces; do not fall back to MiMo.",
    )


def _summary_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {key: 0.0 for key in _metric_keys()}

    def _rate(mask):
        subset = frame[mask]
        if subset.empty:
            return 0.0
        return round(float(subset["process_success"].astype(bool).mean()), 4)

    tools_only_mask = frame["method_id"] == "tools_only"
    mimo_static_mask = (frame["workflow_type"] == "static") & (frame["paper_method_level"].isin(["L4", "B4"]))
    mimo_dynamic_mask = (frame["workflow_type"] == "dynamic") & (frame["paper_method_level"].isin(["L4", "B4"]))
    mimo_rolling_real_mask = (
        (frame["workflow_type"] == "rolling")
        & (frame["paper_method_level"].isin(["L4", "B4"]))
        & (frame["forecast_error_type"].isna())
    )
    rolling_stress_mask = (
        (frame["workflow_type"] == "rolling")
        & (frame["paper_method_level"].isin(["L4", "B4"]))
        & (frame["forecast_error_type"].notna())
    )

    metrics = {
        "tools_only_record_count": int(frame[tools_only_mask].shape[0]),
        "tools_only_success_rate": _rate(tools_only_mask),
        "tools_only_hard_constraint_violation_count": int(
            frame[tools_only_mask & (frame["hard_constraint_violation"].map(_to_bool))].shape[0]
        ),
        "mimo_static_record_count": int(frame[mimo_static_mask].shape[0]),
        "mimo_static_strict_clean_record_count": int(frame[mimo_static_mask & (frame["event_class"] == "strict_clean")].shape[0]),
        "mimo_static_strict_clean_success_rate": _rate(mimo_static_mask & (frame["event_class"] == "strict_clean")),
        "mimo_static_repaired_record_count": int(frame[mimo_static_mask & (frame["event_class"] == "repaired_executable")].shape[0]),
        "mimo_static_repaired_success_rate": _rate(mimo_static_mask & (frame["event_class"] == "repaired_executable")),
        "mimo_dynamic_record_count": int(frame[mimo_dynamic_mask].shape[0]),
        "mimo_dynamic_carry_over_evaluation_rate": _carry_over_evaluation_rate(frame[mimo_dynamic_mask]),
        "mimo_dynamic_protocol_adherence_rate": _bool_rate(frame[mimo_dynamic_mask], "protocol_adherent"),
        "mimo_rolling_real_record_count": int(frame[mimo_rolling_real_mask].shape[0]),
        "mimo_rolling_real_success_rate": _rate(mimo_rolling_real_mask),
        "rolling_stress_record_count": int(frame[rolling_stress_mask].shape[0]),
        "rolling_stress_success_rate": _rate(rolling_stress_mask),
    }
    metrics.update(_mcp_skill_metrics(frame))
    metrics.update(_component_ablation_metrics(frame))
    metrics.update(command_challenge_gate_metrics(frame))
    metrics.update(deepseek_subset_gate_metrics(frame))
    return metrics


def _ensure_gate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    had_hard_column = "hard_constraint_violation" in frame.columns
    defaults = {
        "transport": "",
        "phase": "",
        "hard_constraint_violation": False,
        "mcp_connect_success": False,
        "mcp_tools_list_success": False,
        "mcp_tool_call_count": 0,
        "mcp_tool_call_success_count": 0,
        "structured_output_valid": False,
        "protocol_adherent": False,
        "trigger_reason": None,
        "final_payload_valid": False,
        "forecast_error_type": None,
        "event_class": "",
        "had_carry_over_plan": False,
        "tool_call_chain": "[]",
        "mcp_tool_call_sequence": "[]",
        "executable_plan": False,
        "evaluation_reference_valid": False,
        "command_id": None,
        "command_type": None,
        "command_following_success": False,
        "instruction_status_accuracy": False,
        "is_feasible_command": False,
        "is_infeasible_command": False,
        "is_unsafe_command": False,
        "feasible_command_success": False,
        "unsafe_command_rejected": False,
    }
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
    if not had_hard_column and "safety_status" in frame.columns:
        frame["hard_constraint_violation"] = frame["safety_status"].astype(str).str.contains("hard_constraint_violation")
    return frame


def _mcp_skill_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    mcp = frame[frame["transport"] == "mcp_tools"].copy()
    smoke = mcp[mcp["phase"] == "mcp-skill-smoke"]
    static = mcp[(mcp["phase"] == "mcp-skill-static") & (mcp["workflow_type"] == "static")]
    dynamic = mcp[(mcp["phase"] == "mcp-skill-dynamic") & (mcp["workflow_type"] == "dynamic")]
    rolling = mcp[(mcp["phase"] == "mcp-skill-rolling") & (mcp["workflow_type"] == "rolling") & (mcp["forecast_error_type"].isna())]
    stress = mcp[(mcp["phase"] == "mcp-skill-rolling-stress") & (mcp["workflow_type"] == "rolling") & (mcp["forecast_error_type"].notna())]
    return {
        "mcp_skill_smoke_record_count": int(len(smoke)),
        "mcp_skill_smoke_connect_success_rate": _bool_rate(smoke, "mcp_connect_success"),
        "mcp_skill_smoke_tools_list_success_rate": _bool_rate(smoke, "mcp_tools_list_success"),
        "mcp_skill_smoke_tool_call_success_count": int(smoke["mcp_tool_call_success_count"].fillna(0).sum()) if not smoke.empty else 0,
        "mcp_skill_smoke_final_payload_valid_rate": _bool_rate(smoke, "final_payload_valid"),
        "mcp_skill_static_record_count": int(len(static)),
        "mcp_skill_static_strict_clean_success_rate": _rate_on(static, static["event_class"] == "strict_clean") if not static.empty else 0.0,
        "mcp_skill_static_repaired_success_rate": _rate_on(static, static["event_class"] == "repaired_executable") if not static.empty else 0.0,
        "mcp_skill_static_hard_constraint_violation_count": _hard_count(static),
        "mcp_skill_static_tool_call_success_rate": _mcp_tool_success_rate(static),
        "mcp_skill_static_structured_output_valid_rate": _bool_rate(static, "structured_output_valid"),
        "mcp_skill_static_protocol_adherence_rate": _bool_rate(static, "protocol_adherent"),
        "mcp_skill_dynamic_record_count": int(len(dynamic)),
        "mcp_skill_dynamic_success_rate": _success_rate(dynamic),
        "mcp_skill_dynamic_hard_constraint_violation_count": _hard_count(dynamic),
        "mcp_skill_dynamic_carry_over_evaluation_rate": _carry_over_evaluation_rate(dynamic),
        "mcp_skill_dynamic_protocol_adherence_rate": _bool_rate(dynamic, "protocol_adherent"),
        "mcp_skill_dynamic_tool_call_success_rate": _mcp_tool_success_rate(dynamic),
        "mcp_skill_dynamic_structured_output_valid_rate": _bool_rate(dynamic, "structured_output_valid"),
        "mcp_skill_rolling_record_count": int(len(rolling)),
        "mcp_skill_rolling_success_rate": _success_rate(rolling),
        "mcp_skill_rolling_hard_constraint_violation_count": _hard_count(rolling),
        "mcp_skill_rolling_trigger_reason_coverage_rate": _coverage_rate(rolling, "trigger_reason"),
        "mcp_skill_rolling_tool_call_success_rate": _mcp_tool_success_rate(rolling),
        "mcp_skill_rolling_structured_output_valid_rate": _bool_rate(rolling, "structured_output_valid"),
        "mcp_skill_rolling_stress_record_count": int(len(stress)),
        "mcp_skill_rolling_stress_success_rate": _success_rate(stress),
        "mcp_skill_rolling_stress_hard_constraint_violation_count": _hard_count(stress),
        "mcp_skill_rolling_stress_forecast_error_type_coverage_rate": _coverage_rate(stress, "forecast_error_type"),
        "mcp_skill_rolling_stress_tool_call_success_rate": _mcp_tool_success_rate(stress),
    }


def _component_ablation_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    component = frame[frame["phase"].isin(["component-ablation", "component-ablation-smoke"])].copy()
    b2 = component[component["paper_method_level"] == "L2"]
    b3 = component[component["paper_method_level"] == "B3"]
    b4 = component[component["paper_method_level"] == "B4"]
    b2_failures = b2[~b2["process_success"].map(_to_bool)] if not b2.empty else pd.DataFrame()
    return {
        "component_b2_record_count": int(len(b2)),
        "component_b2_unclassified_failure_count": int(
            b2_failures["failure_reason"].fillna("").astype(str).str.strip().eq("").sum()
        )
        if not b2_failures.empty and "failure_reason" in b2_failures.columns
        else 0,
        "component_b2_executable_plan_rate": _bool_rate(b2, "executable_plan"),
        "component_b3_record_count": int(len(b3)),
        "component_b3_mcp_connect_success_rate": _bool_rate(b3, "mcp_connect_success"),
        "component_b3_mcp_tools_list_success_rate": _bool_rate(b3, "mcp_tools_list_success"),
        "component_b3_mcp_tool_call_success_rate": _mcp_tool_success_rate(b3),
        "component_b3_hard_constraint_violation_count": _hard_count(b3),
        "component_b4_record_count": int(len(b4)),
        "component_b4_success_rate": _success_rate(b4),
        "component_b4_hard_constraint_violation_count": _hard_count(b4),
        "component_b4_protocol_adherence_rate": _bool_rate(b4, "protocol_adherent"),
        "component_b4_structured_output_valid_rate": _bool_rate(b4, "structured_output_valid"),
    }


def _carry_over_evaluation_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    carry = frame[frame["had_carry_over_plan"].astype(bool)].copy()
    if carry.empty:
        return 1.0
    matched = 0
    for _, row in carry.iterrows():
        chain = _parse_chain(row.get("mcp_tool_call_sequence"))
        if not chain:
            chain = _parse_chain(row.get("tool_call_chain"))
        if chain[:2] == ["simulate_release_plan", "evaluate_release_plan"] or chain[:4] == [
            "get_reservoir_status",
            "query_dispatch_rules",
            "simulate_dispatch_program",
            "evaluate_dispatch_result",
        ]:
            matched += 1
    return round(matched / len(carry), 4)


def _parse_chain(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:
            return []
    return []


def _success_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    return round(float(frame["process_success"].astype(bool).mean()), 4)


def _bool_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return round(float(frame[column].fillna(False).astype(bool).mean()), 4)


def _coverage_rate(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return 0.0
    return round(float(frame[column].notna().mean()), 4)


def _rate_on(frame: pd.DataFrame, mask) -> float:
    subset = frame[mask]
    if subset.empty:
        return 1.0
    return _success_rate(subset)


def _hard_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    return int(frame["hard_constraint_violation"].map(_to_bool).sum())


def _mcp_tool_success_rate(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    calls = float(frame["mcp_tool_call_count"].fillna(0).sum())
    if calls == 0:
        return 0.0
    return round(float(frame["mcp_tool_call_success_count"].fillna(0).sum()) / calls, 4)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"true", "1", "yes", "y", "hard_constraint_violation"}


def _metric_keys() -> list[str]:
    return [
        "tools_only_success_rate",
        "tools_only_hard_constraint_violation_count",
        "mimo_static_strict_clean_success_rate",
        "mimo_static_repaired_success_rate",
        "mimo_dynamic_carry_over_evaluation_rate",
        "mimo_dynamic_protocol_adherence_rate",
        "mimo_rolling_real_success_rate",
        "rolling_stress_success_rate",
        "command_b2_record_count",
        "command_b2_evaluation_reference_valid_rate",
        "command_b3_record_count",
        "command_b3_command_following_success_rate",
        "command_b3_evaluation_reference_valid_rate",
        "command_b4_record_count",
        "command_b4_hard_constraint_violation_count",
        "command_b4_structured_output_valid_rate",
        "command_b4_protocol_adherence_rate",
        "command_b4_infeasible_command_detection_rate",
        "command_b4_unsafe_command_rejection_rate",
        "command_b4_command_following_success_rate",
        "command_b4_evaluation_reference_valid_rate",
        "deepseek_record_count",
        "deepseek_success_rate",
        "deepseek_hard_constraint_violation_count",
        "deepseek_mcp_tool_call_success_rate",
        "deepseek_structured_output_valid_rate",
        "deepseek_protocol_adherence_rate",
        "deepseek_command_unsafe_rejection_rate",
        "deepseek_command_infeasible_detection_rate",
    ]


if __name__ == "__main__":
    main()
