"""Stage 3 fail-closed validator: composite acceptance gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from experiments.paper_validation.mcp_skill_runner import (
    collect_available_evaluation_references,
    validate_skill_protocol,
)
from experiments.paper_validation.schema import ReservoirDecisionPayload, validate_structured_payload


@dataclass
class ValidationResult:
    accepted: bool = False
    tool_order_valid: bool = False
    eval_ref_valid: bool = False
    schema_valid: bool = False
    hard_violation: bool = False
    downstream_violation: bool = False
    payload_valid: bool = False
    missing_required_tool: bool = False
    wrong_tool_order: bool = False
    stale_eval_ref: bool = False
    missing_eval_ref: bool = False
    schema_error: str | None = None
    tool_call_error: bool = False
    llm_output_parse_error: bool = False
    failure_reason: str | None = None


def validate_stage3_decision(
    raw_result: dict[str, Any],
    workflow_type: str,
    stage_payload: dict[str, Any],
) -> ValidationResult:
    """Apply fail-closed validation to one Stage 3 LLM result.

    accepted = tool_order_valid AND eval_ref_valid AND schema_valid
               AND NOT hard_violation AND NOT downstream_violation
    """
    vr = ValidationResult()

    tool_chain: list[str] = raw_result.get("mcp_tool_call_sequence") or []
    if not tool_chain:
        # Try alternate key from TrueMcpSkillRunner trace
        tool_chain = [
            str(e.get("tool_name", ""))
            for e in (raw_result.get("llm_execution_trace") or {}).get("tool_events", [])
        ]

    # 1. Tool order validation
    # dynamic_replan/dynamic_retain → dynamic; rolling_replan/rolling_retain → rolling
    base_workflow = workflow_type.split("_")[0] if "_" in workflow_type else workflow_type
    protocol_failure = validate_skill_protocol(
        workflow=base_workflow,
        tool_chain=tool_chain,
        final_payload=None,
        stage_payload=stage_payload,
    )
    vr.tool_order_valid = protocol_failure is None
    if not vr.tool_order_valid:
        vr.wrong_tool_order = True
        vr.missing_required_tool = "missing_required_tool" in (protocol_failure or "")

    # 2. Schema validation
    payload_json = raw_result.get("accepted_evidence_pair", {})
    if isinstance(payload_json, dict):
        payload_json = payload_json.get("final_payload", payload_json)
    decision, schema_err = validate_structured_payload(payload_json)
    vr.schema_valid = decision is not None
    vr.schema_error = schema_err
    vr.llm_output_parse_error = not vr.schema_valid and schema_err == "invalid_final_payload"

    # 3. Evidence binding (eval_ref)
    available_refs_raw = collect_available_evaluation_references(
        raw_result.get("llm_execution_trace", {}).get("tool_events", []),
        stage_payload,
    )
    # available_refs_raw is a list of dicts; extract reference_id strings
    available_ref_ids = {
        str(r.get("reference_id"))
        for r in available_refs_raw
        if r.get("reference_id")
    }
    if decision is not None and decision.evaluation_reference:
        vr.eval_ref_valid = decision.evaluation_reference in available_ref_ids
        vr.stale_eval_ref = not vr.eval_ref_valid
        vr.missing_eval_ref = False
    elif decision is not None:
        # No eval_ref provided — treat as missing
        vr.eval_ref_valid = False
        vr.missing_eval_ref = True
    else:
        vr.eval_ref_valid = False
        vr.missing_eval_ref = True

    # 4. Hard constraint check
    safety = raw_result.get("safety_status") or {}
    if isinstance(safety, dict):
        vr.hard_violation = int(safety.get("hard_constraint_violations_count", 0)) > 0
    elif decision is not None:
        vr.hard_violation = bool(decision.hard_constraint_violation)

    # 5. Downstream violation (from trace or result)
    vr.downstream_violation = bool(raw_result.get("downstream_violation", False))

    # 6. Tool call error
    vr.tool_call_error = bool(raw_result.get("mcp_tool_call_failure_count", 0) > 0)

    # 7. Payload valid (schema + no parse error)
    vr.payload_valid = vr.schema_valid

    # Composite acceptance
    vr.accepted = (
        vr.tool_order_valid
        and vr.eval_ref_valid
        and vr.schema_valid
        and not vr.hard_violation
        and not vr.downstream_violation
    )

    # Failure reason
    if not vr.accepted:
        if not vr.tool_order_valid:
            vr.failure_reason = protocol_failure or "wrong_tool_order"
        elif not vr.eval_ref_valid:
            vr.failure_reason = "missing_eval_ref" if vr.missing_eval_ref else "stale_eval_ref"
        elif not vr.schema_valid:
            vr.failure_reason = schema_err or "schema_invalid"
        elif vr.hard_violation:
            vr.failure_reason = "hard_constraint_violation"
        elif vr.downstream_violation:
            vr.failure_reason = "downstream_violation"
    else:
        vr.failure_reason = None

    return vr
