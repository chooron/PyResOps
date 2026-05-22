"""Stage 3 payload schema: re-exports and Stage 3 specific helpers."""

from __future__ import annotations

from typing import Any

from experiments.paper_validation.schema import (
    ReservoirDecisionPayload,
    validate_structured_payload,
)

__all__ = ["ReservoirDecisionPayload", "validate_structured_payload", "payload_to_stage3_row"]


def payload_to_stage3_row(
    decision: ReservoirDecisionPayload | None,
    trace: dict[str, Any],
    validation_result: "ValidationResult",  # noqa: F821 — forward ref from fail_closed_validator
    event_id: str,
    workflow_type: str,
    workflow_stage: str,
    model_profile: str,
    session_id: str,
) -> dict[str, Any]:
    """Build a unified Stage 3 result row from a decision payload + trace + validation."""
    row: dict[str, Any] = {
        "session_id": session_id,
        "event_id": event_id,
        "scenario_type": workflow_type,
        "workflow_stage": workflow_stage,
        "model_profile": model_profile,
        "llm_called": True,
        "trigger_reason": None,
        # fail-closed composite
        "accepted": validation_result.accepted,
        "tool_order_valid": validation_result.tool_order_valid,
        "eval_ref_valid": validation_result.eval_ref_valid,
        "schema_valid": validation_result.schema_valid,
        "hard_violation": validation_result.hard_violation,
        "downstream_violation": validation_result.downstream_violation,
        "payload_valid": validation_result.payload_valid,
        "missing_required_tool": validation_result.missing_required_tool,
        "wrong_tool_order": validation_result.wrong_tool_order,
        "stale_eval_ref": validation_result.stale_eval_ref,
        "missing_eval_ref": validation_result.missing_eval_ref,
        "schema_error": validation_result.schema_error,
        "tool_call_error": validation_result.tool_call_error,
        "llm_output_parse_error": validation_result.llm_output_parse_error,
        "failure_reason": validation_result.failure_reason,
        # MCP trace fields
        "tool_call_count": trace.get("mcp_tool_call_count", 0),
        "tool_call_sequence": trace.get("mcp_tool_call_sequence", []),
        "protocol_adherence": trace.get("protocol_adherence", False),
        "final_payload_valid": trace.get("final_payload_valid", False),
        "reference_valid": trace.get("reference_valid", False),
        "mcp_connect_success": trace.get("mcp_connect_success", False),
    }

    if decision is not None:
        row.update({
            "decision_type": decision.decision_type,
            "safety_status": decision.safety_status,
            "instruction_status": decision.instruction_status,
            "evaluation_reference": decision.evaluation_reference,
            "selected_plan_id": decision.selected_plan_id,
        })
    else:
        row.update({
            "decision_type": None,
            "safety_status": None,
            "instruction_status": None,
            "evaluation_reference": None,
            "selected_plan_id": None,
        })

    return row
