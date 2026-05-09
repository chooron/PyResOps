"""JSONL result logging for minimal validation runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.workflows import WorkflowStage


class JsonlResultLogger:
    """Append stage-level validation records to JSONL."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def log_stage_result(
        self,
        *,
        run_id: str,
        scenario_set: str,
        scenario_group: str,
        event_id: str,
        workflow_type: str,
        method_id: str,
        model_profile: str,
        stage: WorkflowStage,
        stage_result: dict[str, Any] | None,
        process_success: bool,
        failure_reason: str | None = None,
    ) -> dict[str, Any]:
        record = build_stage_record(
            run_id=run_id,
            scenario_set=scenario_set,
            scenario_group=scenario_group,
            event_id=event_id,
            workflow_type=workflow_type,
            method_id=method_id,
            model_profile=model_profile,
            stage=stage,
            stage_result=stage_result,
            process_success=process_success,
            failure_reason=failure_reason,
        )
        self.append(record)
        return record


def build_stage_record(
    *,
    run_id: str,
    scenario_set: str,
    scenario_group: str,
    event_id: str,
    workflow_type: str,
    method_id: str,
    model_profile: str,
    stage: WorkflowStage,
    stage_result: dict[str, Any] | None,
    process_success: bool,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    result = stage_result or {}
    evaluation_metrics = _extract_metrics(result)
    quality = _data_quality_fields(stage)
    return {
        "run_id": run_id,
        "scenario_set": scenario_set,
        "scenario_group": scenario_group,
        "event_id": event_id,
        "workflow_type": workflow_type,
        "stage_id": stage.stage_id,
        "stage_offset_hours": stage.offset_hours,
        "method_id": method_id,
        "model_profile": model_profile,
        "process_success": bool(process_success),
        "safety_status": result.get("safety_status", {}),
        "instruction_status": result.get("instruction_status", {}),
        "tool_call_chain": result.get("tool_call_chain", []),
        "tool_call_chain_expected": stage.payload.get("agent_workflow_profile"),
        "metrics": evaluation_metrics,
        "failure_reason": failure_reason or result.get("acceptance_failure_reason"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "replan_reason": stage.replan_reason,
        "operator_instruction": stage.operator_instruction,
        "had_carry_over_plan": bool(stage.payload.get("carry_over_plan")),
        "payload_summary": _payload_summary(stage),
        "tool_trace": (result.get("llm_execution_trace") or {}).get("tool_events", []),
        "final_payload": _final_payload(result),
        "raw_result": result,
        **quality,
        "failure_taxonomy": classify_failure_taxonomy(
            failure_reason or result.get("acceptance_failure_reason"),
            result=result,
        ),
    }


def classify_failure_taxonomy(
    failure_reason: str | None,
    *,
    result: dict[str, Any] | None = None,
) -> str | None:
    """Classify failures into the large-validation data/tool/protocol taxonomy."""

    result = result or {}
    reason = str(failure_reason or "").lower()
    safety_status = (result.get("safety_status") or {}).get("status")
    if not reason and safety_status not in {"hard_constraint_violation"}:
        return None
    if reason.startswith("data_quality_blocker"):
        return "data"
    data_markers = (
        "missing required csv column",
        "missing inflow",
        "missing outflow",
        "unexpected_missing_outflow_after_preprocessing",
        "missing required value",
        "invalid time step",
        "non-uniform",
        "non-increasing",
    )
    if any(marker in reason for marker in data_markers):
        return "data"
    protocol_markers = (
        "unexpected_tool_chain",
        "repeated_static_optimization",
        "repeated_static_simulation",
        "repeated_static_evaluation",
        "missing_required_tool",
        "wrong_tool_order",
        "missing_carry_over_evaluation",
        "missing_dynamic",
        "unexpected_dynamic",
        "protocol",
        "non_json",
        "schema",
    )
    if any(marker in reason for marker in protocol_markers):
        return "protocol"
    return "tool"


def _payload_summary(stage: WorkflowStage) -> dict[str, Any]:
    payload = stage.payload
    data_source = payload["data_source"]
    return {
        "scenario_id": payload["id"],
        "source_path": data_source["path"],
        "raw_path": data_source.get("raw_path"),
        "processed_path": data_source.get("processed_path"),
        "start_time": payload["start_time"].isoformat(),
        "duration_hours": payload["duration_hours"],
        "time_step_hours": payload["time_step_hours"],
        "series_length": len(payload["benchmark_inflow_series_m3s"]),
        "uses_synthetic_data": data_source["uses_synthetic_data"],
        "uses_processed_data": bool(data_source.get("uses_processed_data", False)),
        "uses_prediction": "benchmark_predicted_inflow_series_m3s" in payload,
        "had_carry_over_plan": bool(payload.get("carry_over_plan")),
        "missing_inflow_count": int(data_source.get("missing_inflow_count", 0)),
        "missing_outflow_count": int(data_source.get("missing_outflow_count", 0)),
        "outflow_fallback_applied": bool(data_source.get("outflow_fallback_applied", False)),
        "strict_clean_eligible": bool(data_source.get("strict_clean_eligible", True)),
        "repaired_executable_eligible": bool(
            data_source.get("repaired_executable_eligible", True)
        ),
        "diagnostic_only": bool(data_source.get("diagnostic_only", False)),
        "event_class": data_source.get("event_class"),
    }


def _extract_metrics(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("evaluation_metrics"), dict):
        return dict(result["evaluation_metrics"])
    trace = result.get("llm_execution_trace") or {}
    for event in reversed(trace.get("tool_events", []) or []):
        if event.get("tool_name") != "evaluate_dispatch_result":
            continue
        for key in ("result", "output", "content"):
            payload = event.get(key)
            if isinstance(payload, dict):
                return payload
            if isinstance(payload, str):
                try:
                    decoded = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    return decoded
    return {}


def _final_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    accepted = result.get("accepted_evidence_pair")
    if isinstance(accepted, dict) and isinstance(accepted.get("final_payload"), dict):
        return dict(accepted["final_payload"])
    return None


def _data_quality_fields(stage: WorkflowStage) -> dict[str, Any]:
    data_source = stage.payload.get("data_source") or {}
    strict_clean_eligible = bool(data_source.get("strict_clean_eligible", True))
    repaired_executable_eligible = bool(
        data_source.get("repaired_executable_eligible", True)
    )
    event_class = str(
        data_source.get(
            "event_class",
            "strict_clean"
            if strict_clean_eligible
            else "repaired_executable"
            if repaired_executable_eligible
            else "diagnostic_only",
        )
    )
    return {
        "data_quality_status": str(
            data_source.get(
                "data_quality_status",
                event_class,
            )
        ),
        "data_quality_reason": str(data_source.get("data_quality_reason", "") or ""),
        "event_class": event_class,
        "strict_clean_eligible": strict_clean_eligible,
        "repaired_executable_eligible": repaired_executable_eligible,
        "diagnostic_only": bool(data_source.get("diagnostic_only", event_class == "diagnostic_only")),
        "excluded_from_clean_success_denominator": not strict_clean_eligible,
        "excluded_from_repaired_success_denominator": not repaired_executable_eligible,
        "outflow_fallback_applied": bool(data_source.get("outflow_fallback_applied", False)),
    }
