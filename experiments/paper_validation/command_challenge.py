"""Command-challenge configuration, metrics, and audit helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from experiments.paper_validation.schema import validate_structured_payload
from experiments.paper_validation.utils import write_markdown


COMMAND_CONFIG_PATH = Path("experiments/config/command_challenge.yml")
PAPER_RESULTS_ROOT = Path("experiments/results/paper_validation")


def load_command_challenge_config(path: str | Path = COMMAND_CONFIG_PATH) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Missing command challenge config: {resolved}")
    with resolved.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"Command challenge config must be a mapping: {resolved}")
    for section in ("static_cases", "dynamic_cases", "rolling_cases"):
        if not isinstance(cfg.get(section), list):
            raise ValueError(f"Command challenge config must define list section: {section}")
    for case in iter_command_cases(cfg):
        missing = [
            field
            for field in (
                "command_id",
                "command_type",
                "event_id",
                "workflow",
                "command_text",
                "expected_instruction_status",
            )
            if field not in case or case[field] in {None, ""}
        ]
        if missing:
            raise ValueError(f"Command case {case.get('command_id', '<unknown>')} is missing {missing}")
    return cfg


def iter_command_cases(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for section in ("static_cases", "dynamic_cases", "rolling_cases"):
        for raw in cfg.get(section, []) or []:
            case = dict(raw)
            case["workflow"] = str(case.get("workflow") or section.removesuffix("_cases"))
            case["expected_hard_violation_allowed"] = bool(case.get("expected_hard_violation_allowed", False))
            case["requires_replan"] = bool(case.get("requires_replan", False))
            case["expected_safe_rejection"] = bool(case.get("expected_safe_rejection", False))
            cases.append(case)
    return cases


def group_dynamic_command_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if str(case.get("workflow")) != "dynamic":
            continue
        grouped.setdefault(str(case["event_id"]), []).append(case)
    return [
        {
            "event_id": event_id,
            "workflow": "dynamic",
            "stage_offsets": tuple(sorted(int(item["stage_id"]) for item in items)),
            "instructions": {int(item["stage_id"]): str(item["command_text"]) for item in items},
            "command_cases": {f"dynamic_{int(item['stage_id'])}h": item for item in items},
        }
        for event_id, items in sorted(grouped.items())
    ]


def group_rolling_command_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if str(case.get("workflow")) != "rolling":
            continue
        grouped.setdefault(str(case["event_id"]), []).append(case)
    return [
        {
            "event_id": event_id,
            "workflow": "rolling",
            "command_cases": {f"rolling_{int(item['stage_id'])}h": item for item in items},
            "rolling_event_path": str(items[0].get("rolling_event_path") or "data/withpred/2024072617.csv"),
        }
        for event_id, items in sorted(grouped.items())
    ]


def command_case_prompt_fields(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "command_id": case.get("command_id"),
        "command_type": case.get("command_type"),
        "command_text": case.get("command_text"),
        "evaluation_focus": case.get("evaluation_focus"),
        "notes": case.get("notes"),
    }


def enrich_record_with_command_metrics(record: dict[str, Any], command_case: dict[str, Any] | None) -> None:
    if not command_case:
        return
    for field in (
        "command_id",
        "command_type",
        "command_text",
        "expected_instruction_status",
        "requires_replan",
        "expected_safe_rejection",
        "expected_hard_violation_allowed",
        "evaluation_focus",
        "notes",
    ):
        if field in command_case:
            record[field] = command_case[field]

    final_payload = record.get("final_payload") if isinstance(record.get("final_payload"), dict) else {}
    decision_type = str(final_payload.get("decision_type") or "")
    instruction_status = str(final_payload.get("instruction_status") or _runtime_instruction_status(record))
    expected = _expected_statuses(command_case.get("expected_instruction_status"))
    hard_violation = _bool_value(record.get("hard_constraint_violation"))
    safe_rejection = decision_type == "reject_infeasible" or instruction_status == "infeasible"
    command_type = str(command_case.get("command_type") or "")
    infeasible_command = command_type.startswith("C7_") or "physically_infeasible" in command_type
    unsafe_command = command_type.startswith("C6_") or "conflicting_safety" in command_type
    expected_safe_rejection = bool(command_case.get("expected_safe_rejection"))
    structured = _bool_value(record.get("structured_output_valid"))
    protocol = _bool_value(record.get("protocol_adherent"))
    eval_ref_valid = _bool_value(record.get("evaluation_reference_valid"))
    if final_payload.get("evaluation_reference") and not record.get("evaluation_reference_valid"):
        eval_ref_valid = not _bool_value(record.get("hallucinated_value"))
    expected_status_ok = instruction_status in expected if expected else bool(instruction_status)
    if expected_safe_rejection:
        expected_status_ok = safe_rejection
    if command_type.startswith("C8_") and structured and not hard_violation:
        expected_status_ok = True
    if command_type.startswith("C1_") and safe_rejection and not hard_violation:
        expected_status_ok = True
    replan_required = bool(command_case.get("requires_replan"))
    replan_selected = decision_type in {"accept", "replan"} or _bool_value(record.get("whether_replan"))
    if decision_type == "retain_carry_over":
        replan_selected = False
    replan_ok = bool(replan_selected == replan_required)
    if expected_safe_rejection:
        replan_ok = True

    no_unsafe_accept = not hard_violation and not (expected_safe_rejection and decision_type != "reject_infeasible")
    feasible_command = not expected_safe_rejection and not infeasible_command and not unsafe_command and not safe_rejection
    feasible_success = (
        structured
        and no_unsafe_accept
        and expected_status_ok
        and (eval_ref_valid or command_type.startswith("C8_"))
    )
    rejection_success = structured and safe_rejection and not hard_violation
    command_success = rejection_success if expected_safe_rejection else feasible_success

    record["instruction_status_label"] = instruction_status
    record["decision_type"] = decision_type
    record["safe_rejection"] = rejection_success
    record["instruction_status_accuracy"] = expected_status_ok
    record["replan_necessity_accuracy"] = replan_ok
    record["is_feasible_command"] = feasible_command
    record["is_infeasible_command"] = infeasible_command
    record["is_unsafe_command"] = unsafe_command
    record["feasible_command_success"] = feasible_success if feasible_command else False
    record["infeasible_command_detected"] = rejection_success if infeasible_command else False
    record["unsafe_command_rejected"] = rejection_success if unsafe_command else False
    record["safe_rejection_rate_member"] = rejection_success if expected_safe_rejection else False
    record["command_following_success"] = bool(command_success)
    if expected_safe_rejection and rejection_success:
        record["process_success"] = True
        record["failure_reason"] = None
        record["failure_taxonomy"] = None
    if not bool(command_success) and not record.get("failure_reason"):
        record["failure_reason"] = _command_failure_reason(record, command_case)
        record["failure_taxonomy"] = _command_failure_taxonomy(record["failure_reason"])


def export_command_challenge_tables(frame: pd.DataFrame, tables_root: str | Path) -> None:
    root = Path(tables_root)
    root.mkdir(parents=True, exist_ok=True)
    command = _command_frame(frame)
    _command_summary_table(command, root / "command_challenge_summary.csv")
    _command_failure_taxonomy_table(command, root / "command_challenge_failure_taxonomy.csv")


def export_cross_model_tables(frame: pd.DataFrame, tables_root: str | Path) -> None:
    root = Path(tables_root)
    root.mkdir(parents=True, exist_ok=True)
    _cross_model_summary_table(frame, root / "cross_model_subset_summary.csv")
    _deepseek_failure_taxonomy_table(frame, root / "deepseek_subset_failure_taxonomy.csv")


def command_challenge_gate_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    command = _command_frame(frame)
    b2 = command[command["paper_method_level"] == "L2"]
    b3 = command[command["paper_method_level"] == "B3"]
    b4 = command[command["paper_method_level"] == "B4"]
    return {
        "command_b2_record_count": int(len(b2)),
        "command_b2_evaluation_reference_valid_rate": _rate(b2, "evaluation_reference_valid"),
        "command_b3_record_count": int(len(b3)),
        "command_b3_command_following_success_rate": _rate(b3, "command_following_success"),
        "command_b3_evaluation_reference_valid_rate": _rate(b3, "evaluation_reference_valid"),
        "command_b4_record_count": int(len(b4)),
        "command_b4_hard_constraint_violation_count": _hard_count(b4),
        "command_b4_structured_output_valid_rate": _rate(b4, "structured_output_valid"),
        "command_b4_protocol_adherence_rate": _rate(b4, "protocol_adherent"),
        "command_b4_infeasible_command_detection_rate": _conditional_rate(
            b4,
            "is_infeasible_command",
            "infeasible_command_detected",
        ),
        "command_b4_unsafe_command_rejection_rate": _conditional_rate(
            b4,
            "is_unsafe_command",
            "unsafe_command_rejected",
        ),
        "command_b4_command_following_success_rate": _rate(b4, "command_following_success"),
        "command_b4_evaluation_reference_valid_rate": _rate(b4, "evaluation_reference_valid"),
    }


def deepseek_subset_gate_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    subset = frame[frame["phase"] == "deepseek-mcp-skill-subset"].copy() if "phase" in frame.columns else frame.copy()
    command = _command_frame(subset)
    return {
        "deepseek_record_count": int(len(subset)),
        "deepseek_success_rate": _rate(subset, "process_success"),
        "deepseek_hard_constraint_violation_count": _hard_count(subset),
        "deepseek_mcp_tool_call_success_rate": _tool_call_success_rate(subset),
        "deepseek_structured_output_valid_rate": _rate(subset, "structured_output_valid"),
        "deepseek_protocol_adherence_rate": _rate(subset, "protocol_adherent"),
        "deepseek_command_unsafe_rejection_rate": _conditional_rate(
            command,
            "is_unsafe_command",
            "unsafe_command_rejected",
        ),
        "deepseek_command_infeasible_detection_rate": _conditional_rate(
            command,
            "is_infeasible_command",
            "infeasible_command_detected",
        ),
    }


def write_deepseek_status_report(
    *,
    frame: pd.DataFrame,
    output_path: str | Path,
    model_profile: str | None,
    base_url: str | None,
    gate_result: dict[str, Any] | None,
    comparison_frame: pd.DataFrame | None = None,
) -> Path:
    lines = [
        "# DeepSeek MCPTools + Skill Subset Status",
        "",
        f"- Model profile: `{model_profile or ''}`",
        f"- Base URL: `{base_url or ''}`",
        f"- Uses DEEPSEEK_API_KEY: `{bool(os.getenv('DEEPSEEK_API_KEY'))}`",
        "- GPT / Claude external strong-model validation is reserved for a later pre-submission phase and is not executed in the current cost-controlled batch.",
        "",
    ]
    for workflow in ("static", "dynamic", "rolling"):
        group = frame[frame["workflow_type"] == workflow] if "workflow_type" in frame.columns else pd.DataFrame()
        lines.extend([f"## {workflow.title()} Subset", ""])
        lines.append(_markdown_metric_line(group))
        lines.append("")
    command = _command_frame(frame)
    lines.extend(["## Command Challenge", "", _markdown_metric_line(command), ""])
    if comparison_frame is not None and not comparison_frame.empty:
        mimo = comparison_frame[comparison_frame["paper_method_level"] == "B4"].copy()
        lines.extend(["## MiMo B4 Comparison", "", _markdown_metric_line(mimo), ""])
    lines.extend(["## Gate", "", f"- Status: `{(gate_result or {}).get('status', 'UNKNOWN')}`", ""])
    failures = (gate_result or {}).get("failures") or []
    if failures:
        lines.append("## Gate Failures")
        lines.append("")
        for item in failures:
            lines.append(f"- {item.get('gate')}: `{item.get('metric')}`")
        lines.append("")
    lines.extend(["## Failure Taxonomy", ""])
    failing = frame[~_bool_series(frame.get("process_success", pd.Series(dtype=bool)))] if not frame.empty else pd.DataFrame()
    if failing.empty:
        lines.append("- No failed records.")
    else:
        for reason, group in failing.groupby("failure_reason", dropna=False):
            lines.append(f"- {reason}: {len(group)}")
    lines.extend(["", "## Next Steps", "", "- Use GPT / Claude placeholders only in a later pre-submission external validation batch."])
    return write_markdown(output_path, "\n".join(lines))


def write_phase_g_status_report(
    *,
    output_path: str | Path,
    changed_files: list[str],
    command_frame: pd.DataFrame,
    deepseek_frame: pd.DataFrame,
    payload_repair_frame: pd.DataFrame | None = None,
    command_gate: dict[str, Any] | None = None,
    deepseek_gate: dict[str, Any] | None = None,
) -> Path:
    lines = [
        "# Phase G Current Status",
        "",
        "## Modified Files",
        "",
    ]
    lines.extend(f"- `{path}`" for path in changed_files)
    lines.extend(
        [
            "",
            "## Command Challenge",
            "",
            f"- Records: {len(command_frame)}",
            f"- Command types: {sorted(command_frame['command_type'].dropna().unique()) if 'command_type' in command_frame.columns and not command_frame.empty else []}",
            f"- MiMo B2/B3/B4 summary: {_compact_method_summary(command_frame)}",
            f"- Gate: `{(command_gate or {}).get('status', 'UNKNOWN')}`",
            "",
            "## DeepSeek Subset",
            "",
            "- Added profiles: `deepseek_v4_pro`, `deepseek_v4_flash`.",
            f"- Actual model profiles: {sorted(deepseek_frame['model_profile'].dropna().unique()) if 'model_profile' in deepseek_frame.columns and not deepseek_frame.empty else []}",
            f"- Static: {_compact_workflow_summary(deepseek_frame, 'static')}",
            f"- Dynamic: {_compact_workflow_summary(deepseek_frame, 'dynamic')}",
            f"- Rolling: {_compact_workflow_summary(deepseek_frame, 'rolling')}",
            f"- Command challenge: {_markdown_metric_line(_command_frame(deepseek_frame))}",
            f"- Gate: `{(deepseek_gate or {}).get('status', 'UNKNOWN')}`",
            "",
            "## Payload Repair Audit",
            "",
            f"- Records: {0 if payload_repair_frame is None else len(payload_repair_frame)}",
            f"- Repair success rate: {_rate(payload_repair_frame if payload_repair_frame is not None else pd.DataFrame(), 'repair_success')}",
            "",
            "## Tables And Reports",
            "",
            "- `experiments/results/paper_validation/tables/command_challenge_summary.csv`",
            "- `experiments/results/paper_validation/tables/command_challenge_failure_taxonomy.csv`",
            "- `experiments/results/paper_validation/tables/cross_model_subset_summary.csv`",
            "- `experiments/results/paper_validation/tables/deepseek_subset_failure_taxonomy.csv`",
            "- `experiments/results/paper_validation/tables/payload_repair_audit.csv`",
            "- `experiments/results/paper_validation/deepseek_subset_current_status.md`",
            "",
            "## Recommendation",
            "",
            "- GPT / Claude external strong-model validation is reserved for a later pre-submission phase and is not executed in the current cost-controlled batch.",
        ]
    )
    return write_markdown(output_path, "\n".join(lines))


def build_payload_repair_audit_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        original_valid = _bool_value(record.get("final_payload_valid")) or _bool_value(record.get("structured_output_valid"))
        if original_valid:
            continue
        raw_result = record.get("raw_result") if isinstance(record.get("raw_result"), dict) else {}
        raw_text = str(raw_result.get("final_decision_text") or record.get("final_decision_text") or "")
        original_payload = record.get("final_payload")
        _, original_error = validate_structured_payload(original_payload if isinstance(original_payload, dict) else None)
        repaired_payload = _repair_payload_schema_only(record, original_payload if isinstance(original_payload, dict) else {})
        _, repaired_error = validate_structured_payload(repaired_payload)
        repair_success = repaired_error is None
        rows.append(
            {
                "run_id": record.get("run_id"),
                "method_level": record.get("paper_method_level"),
                "model_profile": record.get("model_profile"),
                "workflow": record.get("workflow_type"),
                "event_id": record.get("event_id"),
                "command_id": record.get("command_id"),
                "original_valid": False,
                "repair_attempted": True,
                "repair_success": repair_success,
                "original_error": original_error or record.get("final_payload_validation_error") or record.get("failure_reason"),
                "original_invalid_payload": json.dumps(original_payload, ensure_ascii=False, default=str)
                if original_payload is not None
                else raw_text,
                "repaired_payload": json.dumps(repaired_payload, ensure_ascii=False, default=str),
                "final_status_after_repair": "valid_after_repair" if repair_success else "invalid_after_repair",
                "payload_repair_attempted": True,
                "payload_repair_success": repair_success,
                "repaired_payload_valid": repair_success,
                "repair_model_profile": record.get("model_profile"),
                "repair_did_not_call_tools": True,
            }
        )
    return rows


def _repair_payload_schema_only(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(payload)
    repaired.setdefault("event_id", str(record.get("event_id") or "unknown"))
    repaired.setdefault("workflow", str(record.get("workflow_type") or "static"))
    if repaired["workflow"] not in {"static", "dynamic", "rolling"}:
        repaired["workflow"] = "static"
    repaired.setdefault("stage_id", str(record.get("stage_id") or "unknown"))
    repaired.setdefault("method_level", str(record.get("paper_method_level") or record.get("method_level") or "unknown"))
    decision_type = str(repaired.get("decision_type") or record.get("decision_type") or "accept")
    if decision_type not in {"accept", "retain_carry_over", "replan", "reject_infeasible"}:
        decision_type = "accept"
    repaired["decision_type"] = decision_type
    repaired.setdefault("selected_plan_id", None)
    target_summary = repaired.get("target_release_summary")
    if not isinstance(target_summary, dict):
        target_summary = {}
    target_summary.setdefault("target_release_m3s", 0.0)
    repaired["target_release_summary"] = target_summary
    safety = str(repaired.get("safety_status") or "unknown")
    repaired["safety_status"] = safety if safety in {"safe", "unsafe", "unknown"} else "unknown"
    repaired["hard_constraint_violation"] = _bool_value(repaired.get("hard_constraint_violation"))
    status = str(repaired.get("instruction_status") or "not_applicable")
    if status not in {"satisfied", "partially_satisfied", "in_progress", "infeasible", "not_applicable"}:
        status = "not_applicable"
    repaired["instruction_status"] = status
    for field in ("tool_chain_summary", "mcp_tool_chain_summary"):
        if not isinstance(repaired.get(field), list):
            repaired[field] = []
    repaired.setdefault("evaluation_reference", None)
    repaired.setdefault("failure_reason", record.get("failure_reason"))
    repaired.setdefault("explanation", "Schema-only repair preserved original decision semantics.")
    if not isinstance(repaired.get("explanation"), str):
        repaired["explanation"] = str(repaired["explanation"])
    return repaired


def _command_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "command_id" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["command_id"].notna() & frame["command_id"].astype(str).str.len().gt(0)].copy()


def _command_summary_table(frame: pd.DataFrame, output_path: Path) -> None:
    rows = []
    if not frame.empty:
        for (method_level, workflow, command_type), group in frame.groupby(
            ["paper_method_level", "workflow_type", "command_type"],
            dropna=False,
        ):
            rows.append(
                {
                    "method_level": method_level,
                    "workflow": workflow,
                    "command_type": command_type,
                    "records": len(group),
                    "success_rate": _rate(group, "process_success"),
                    "feasible_command_success_rate": _conditional_rate(
                        group,
                        "is_feasible_command",
                        "feasible_command_success",
                    ),
                    "infeasible_command_detection_rate": _conditional_rate(
                        group,
                        "is_infeasible_command",
                        "infeasible_command_detected",
                    ),
                    "unsafe_command_rejection_rate": _conditional_rate(
                        group,
                        "is_unsafe_command",
                        "unsafe_command_rejected",
                    ),
                    "command_following_success_rate": _rate(group, "command_following_success"),
                    "instruction_status_accuracy": _rate(group, "instruction_status_accuracy"),
                    "hard_constraint_violation_count": _hard_count(group),
                    "evaluation_reference_valid_rate": _rate(group, "evaluation_reference_valid"),
                    "structured_output_valid_rate": _rate(group, "structured_output_valid"),
                    "protocol_adherence_rate": _rate(group, "protocol_adherent"),
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _command_failure_taxonomy_table(frame: pd.DataFrame, output_path: Path) -> None:
    failing = frame[~_bool_series(frame["command_following_success"])] if not frame.empty else pd.DataFrame()
    rows = []
    if not failing.empty:
        for (method_level, workflow, command_type, taxonomy, reason), group in failing.groupby(
            ["paper_method_level", "workflow_type", "command_type", "failure_taxonomy", "failure_reason"],
            dropna=False,
        ):
            rows.append(
                {
                    "method_level": method_level,
                    "workflow": workflow,
                    "command_type": command_type,
                    "failure_taxonomy": taxonomy,
                    "failure_reason": reason,
                    "count": len(group),
                    "example_event_ids": ",".join(sorted(set(group["event_id"].astype(str)))[:5]),
                    "example_command_ids": ",".join(sorted(set(group["command_id"].astype(str)))[:5]),
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _cross_model_summary_table(frame: pd.DataFrame, output_path: Path) -> None:
    rows = []
    if not frame.empty:
        for (profile, method_level, workflow), group in frame.groupby(
            ["model_profile", "paper_method_level", "workflow_type"],
            dropna=False,
        ):
            rows.append(
                {
                    "model_profile": profile,
                    "method_level": method_level,
                    "workflow": workflow,
                    "records": len(group),
                    "success_rate": _rate(group, "process_success"),
                    "hard_constraint_violation_count": _hard_count(group),
                    "mcp_tool_call_success_rate": _tool_call_success_rate(group),
                    "structured_output_valid_rate": _rate(group, "structured_output_valid"),
                    "protocol_adherence_rate": _rate(group, "protocol_adherent"),
                    "command_following_success_rate": _rate(_command_frame(group), "command_following_success"),
                    "infeasible_command_detection_rate": _conditional_rate(
                        _command_frame(group),
                        "is_infeasible_command",
                        "infeasible_command_detected",
                    ),
                    "unsafe_command_rejection_rate": _conditional_rate(
                        _command_frame(group),
                        "is_unsafe_command",
                        "unsafe_command_rejected",
                    ),
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _deepseek_failure_taxonomy_table(frame: pd.DataFrame, output_path: Path) -> None:
    failing = frame[~_bool_series(frame["process_success"])] if not frame.empty and "process_success" in frame else pd.DataFrame()
    if not failing.empty and "command_type" not in failing.columns:
        failing["command_type"] = ""
    rows = []
    if not failing.empty:
        for (profile, workflow, command_type, taxonomy, reason), group in failing.groupby(
            ["model_profile", "workflow_type", "command_type", "failure_taxonomy", "failure_reason"],
            dropna=False,
        ):
            rows.append(
                {
                    "model_profile": profile,
                    "workflow": workflow,
                    "command_type": command_type,
                    "failure_taxonomy": taxonomy,
                    "failure_reason": reason,
                    "count": len(group),
                    "example_event_ids": ",".join(sorted(set(group["event_id"].astype(str)))[:5]),
                    "example_command_ids": ",".join(sorted(set(group.get("command_id", pd.Series(dtype=str)).dropna().astype(str)))[:5]),
                }
            )
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")


def _markdown_metric_line(group: pd.DataFrame) -> str:
    if group is None or group.empty:
        return "- Records: 0"
    return (
        f"- Records: {len(group)}, success: {_rate(group, 'process_success'):.2%}, "
        f"hard violations: {_hard_count(group)}, structured: {_rate(group, 'structured_output_valid'):.2%}, "
        f"protocol: {_rate(group, 'protocol_adherent'):.2%}"
    )


def _compact_method_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or "paper_method_level" not in frame.columns:
        return {}
    return {
        str(level): {
            "records": len(group),
            "command_following_success_rate": _rate(group, "command_following_success"),
            "hard_constraint_violation_count": _hard_count(group),
        }
        for level, group in frame.groupby("paper_method_level", dropna=False)
    }


def _compact_workflow_summary(frame: pd.DataFrame, workflow: str) -> str:
    if frame.empty or "workflow_type" not in frame.columns:
        return "records=0"
    return _markdown_metric_line(frame[frame["workflow_type"] == workflow])


def _expected_statuses(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "")
    separators = ["|", ",", "/"]
    values = [text]
    for sep in separators:
        if sep in text:
            values = text.split(sep)
            break
    return {item.strip() for item in values if item.strip()}


def _runtime_instruction_status(record: dict[str, Any]) -> str:
    value = record.get("instruction_status")
    if isinstance(value, dict):
        status = str(value.get("status") or "")
        mapping = {"completed": "satisfied", "infeasible": "infeasible", "in_progress": "in_progress"}
        return mapping.get(status, status)
    return str(value or "")


def _command_failure_reason(record: dict[str, Any], command_case: dict[str, Any]) -> str:
    if _bool_value(record.get("hard_constraint_violation")):
        return "unsafe_plan_accepted"
    if bool(command_case.get("expected_safe_rejection")) and not _bool_value(record.get("safe_rejection")):
        return "infeasible_instruction_not_rejected"
    if not _bool_value(record.get("structured_output_valid")):
        return "invalid_final_payload"
    if not _bool_value(record.get("evaluation_reference_valid")) and not str(command_case.get("command_type", "")).startswith("C8_"):
        return "missing_or_invalid_evaluation_reference"
    if not _bool_value(record.get("instruction_status_accuracy")):
        return "instruction_status_mismatch"
    if not _bool_value(record.get("replan_necessity_accuracy")):
        return "replan_necessity_mismatch"
    return "command_not_satisfied"


def _command_failure_taxonomy(reason: str) -> str:
    if reason in {"unsafe_plan_accepted", "infeasible_instruction_not_rejected"}:
        return "safety"
    if reason in {"invalid_final_payload", "missing_or_invalid_evaluation_reference"}:
        return "payload"
    if "replan" in reason or "instruction" in reason:
        return "command_following"
    return "tool"


def _rate(group: pd.DataFrame, column: str) -> float:
    if group is None or group.empty or column not in group.columns:
        return 0.0
    return round(float(_bool_series(group[column]).mean()), 4)


def _conditional_rate(group: pd.DataFrame, condition_column: str, outcome_column: str) -> float:
    if group is None or group.empty or condition_column not in group.columns:
        return 0.0
    subset = group[_bool_series(group[condition_column])]
    if subset.empty:
        return 1.0
    return _rate(subset, outcome_column)


def _hard_count(group: pd.DataFrame) -> int:
    if group is None or group.empty or "hard_constraint_violation" not in group.columns:
        return 0
    return int(_bool_series(group["hard_constraint_violation"]).sum())


def _tool_call_success_rate(group: pd.DataFrame) -> float:
    if group is None or group.empty or "mcp_tool_call_count" not in group.columns:
        return 0.0
    calls = pd.to_numeric(group["mcp_tool_call_count"], errors="coerce").fillna(0).sum()
    if calls == 0:
        return 0.0
    success_values = (
        group["mcp_tool_call_success_count"]
        if "mcp_tool_call_success_count" in group.columns
        else pd.Series([0] * len(group))
    )
    successes = pd.to_numeric(success_values, errors="coerce").fillna(0).sum()
    return round(float(successes) / float(calls), 4)


def _bool_series(series: pd.Series) -> pd.Series:
    return series.map(_bool_value)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pass", "passed"}
