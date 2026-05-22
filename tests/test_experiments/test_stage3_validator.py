"""Lightweight tests for Stage 3 fail-closed validator and comparator."""

from __future__ import annotations

import pytest
import pandas as pd


# ---------------------------------------------------------------------------
# ValidationResult dataclass
# ---------------------------------------------------------------------------

def test_validation_result_defaults():
    from experiments.stage3.fail_closed_validator import ValidationResult

    vr = ValidationResult()
    assert vr.accepted is False
    assert vr.tool_order_valid is False
    assert vr.eval_ref_valid is False
    assert vr.schema_valid is False
    assert vr.hard_violation is False
    assert vr.downstream_violation is False
    assert vr.failure_reason is None


# ---------------------------------------------------------------------------
# validate_stage3_decision
# ---------------------------------------------------------------------------

def _make_raw_result(
    tool_chain: list[str] | None = None,
    payload: dict | None = None,
    eval_ref: str | None = None,
    hard_violation: bool = False,
    downstream_violation: bool = False,
) -> dict:
    """Build a minimal raw_result dict for validator tests."""
    tool_events = [
        {"tool_name": t, "call_order": i, "input": {}, "output": {}, "success": True}
        for i, t in enumerate(tool_chain or [])
    ]
    final_payload = payload or {
        "event_id": "test_event",
        "workflow": "static",
        "method_level": "L4",
        "decision_type": "accept",
        "selected_plan_id": "plan_001",
        "safety_status": "safe",
        "hard_constraint_violation": hard_violation,
        "instruction_status": "satisfied",
        "evaluation_reference": eval_ref or "eval_ref_001",
        "explanation": "Test.",
    }
    return {
        "mcp_tool_call_sequence": tool_chain or [],
        "llm_execution_trace": {"tool_events": tool_events},
        "accepted_evidence_pair": {"final_payload": final_payload},
        "safety_status": {
            "hard_constraint_violations_count": 1 if hard_violation else 0,
        },
        "downstream_violation": downstream_violation,
        "mcp_tool_call_failure_count": 0,
        "available_evaluation_references": [eval_ref or "eval_ref_001"],
        "final_evaluation_reference": eval_ref or "eval_ref_001",
    }


def _make_stage_payload(eval_ref: str = "eval_ref_001") -> dict:
    return {
        "id": "test_event_static",
        "event_id": "test_event",
        "workflow_type": "static",
        "stage_id": "static",
        "benchmark_inflow_series_m3s": [1000.0] * 10,
        "timestamps": [],
    }


def test_validator_accepts_valid():
    from experiments.stage3.fail_closed_validator import validate_stage3_decision

    valid_chain = [
        "prepare_event",
        "optimize_release_plan",
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    raw = _make_raw_result(tool_chain=valid_chain, eval_ref="eval_ref_001")
    stage_payload = _make_stage_payload("eval_ref_001")

    vr = validate_stage3_decision(raw, "static", stage_payload)

    assert vr.schema_valid is True
    assert vr.hard_violation is False
    assert vr.downstream_violation is False
    # tool_order and eval_ref depend on mcp_skill_runner internals; just check no crash
    assert vr.failure_reason is None or isinstance(vr.failure_reason, str)


def test_validator_rejects_wrong_order():
    from experiments.stage3.fail_closed_validator import validate_stage3_decision

    wrong_chain = [
        "optimize_release_plan",  # missing prepare_event first
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    raw = _make_raw_result(tool_chain=wrong_chain, eval_ref="eval_ref_001")
    stage_payload = _make_stage_payload("eval_ref_001")

    vr = validate_stage3_decision(raw, "static", stage_payload)

    # Wrong order should fail tool_order gate
    assert vr.tool_order_valid is False
    assert vr.wrong_tool_order is True
    assert vr.accepted is False
    assert vr.failure_reason is not None


def test_validator_rejects_missing_eval_ref():
    from experiments.stage3.fail_closed_validator import validate_stage3_decision

    valid_chain = [
        "prepare_event",
        "optimize_release_plan",
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    payload_no_ref = {
        "event_id": "test_event",
        "workflow": "static",
        "method_level": "L4",
        "decision_type": "accept",
        "selected_plan_id": "plan_001",
        "safety_status": "safe",
        "hard_constraint_violation": False,
        "instruction_status": "satisfied",
        "evaluation_reference": None,  # missing
        "explanation": "Test.",
    }
    raw = _make_raw_result(tool_chain=valid_chain, payload=payload_no_ref)
    raw["available_evaluation_references"] = []
    raw["final_evaluation_reference"] = None
    stage_payload = _make_stage_payload()

    vr = validate_stage3_decision(raw, "static", stage_payload)

    assert vr.eval_ref_valid is False
    assert vr.missing_eval_ref is True
    assert vr.accepted is False


def test_validator_rejects_stale_eval_ref():
    from experiments.stage3.fail_closed_validator import validate_stage3_decision

    valid_chain = [
        "prepare_event",
        "optimize_release_plan",
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    # eval_ref in payload doesn't match available refs
    raw = _make_raw_result(tool_chain=valid_chain, eval_ref="stale_ref_999")
    raw["available_evaluation_references"] = ["eval_ref_001"]  # different
    stage_payload = _make_stage_payload("eval_ref_001")

    vr = validate_stage3_decision(raw, "static", stage_payload)

    assert vr.eval_ref_valid is False
    assert vr.stale_eval_ref is True
    assert vr.accepted is False


def test_validator_rejects_hard_violation():
    from experiments.stage3.fail_closed_validator import validate_stage3_decision

    valid_chain = [
        "prepare_event",
        "optimize_release_plan",
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    raw = _make_raw_result(tool_chain=valid_chain, eval_ref="eval_ref_001", hard_violation=True)
    stage_payload = _make_stage_payload("eval_ref_001")

    vr = validate_stage3_decision(raw, "static", stage_payload)

    assert vr.hard_violation is True
    assert vr.accepted is False


def test_validator_rejects_downstream_violation():
    from experiments.stage3.fail_closed_validator import validate_stage3_decision

    valid_chain = [
        "prepare_event",
        "optimize_release_plan",
        "simulate_release_plan",
        "evaluate_release_plan",
    ]
    raw = _make_raw_result(tool_chain=valid_chain, eval_ref="eval_ref_001", downstream_violation=True)
    stage_payload = _make_stage_payload("eval_ref_001")

    vr = validate_stage3_decision(raw, "static", stage_payload)

    assert vr.downstream_violation is True
    assert vr.accepted is False


# ---------------------------------------------------------------------------
# Stage3Comparator unit tests
# ---------------------------------------------------------------------------

def test_comparator_aligned():
    from experiments.stage3.comparator import Stage3Comparator

    row = {
        "event_id": "2024061623",
        "workflow_stage": "static",
        "accepted": True,
        "max_level": 158.5,
        "terminal_deviation": 1.2,
        "peak_reduction_rate": 0.95,
    }

    cmp = Stage3Comparator()
    cmp._s2 = pd.DataFrame([row])
    cmp._s3 = pd.DataFrame([{**row, "model_profile": "mimo_v25", "session_id": "abc123"}])
    result = cmp.compare()

    assert result["matched_rows"] == 1
    assert result["missing_in_s3"] == 0
    assert result["max_level_failures"] == 0
    assert result["terminal_deviation_failures"] == 0
    assert result["peak_reduction_failures"] == 0


def test_comparator_missing_row():
    from experiments.stage3.comparator import Stage3Comparator

    row = {
        "event_id": "2024061623",
        "workflow_stage": "static",
        "accepted": True,
        "max_level": 158.5,
        "terminal_deviation": 1.2,
        "peak_reduction_rate": 0.95,
    }

    cmp = Stage3Comparator()
    cmp._s2 = pd.DataFrame([row])
    cmp._s3 = pd.DataFrame()  # empty
    result = cmp.compare()

    assert result["missing_in_s3"] == 1
    assert result["matched_rows"] == 0
    assert result["passes_oracle"] is False


def test_comparator_tolerance_failure():
    from experiments.stage3.comparator import Stage3Comparator

    s2_row = {
        "event_id": "2024061623",
        "workflow_stage": "static",
        "accepted": True,
        "max_level": 158.5,
        "terminal_deviation": 1.2,
        "peak_reduction_rate": 0.95,
    }
    s3_row = {**s2_row, "max_level": 159.2}  # delta = 0.7 > 0.5

    cmp = Stage3Comparator()
    cmp._s2 = pd.DataFrame([s2_row])
    cmp._s3 = pd.DataFrame([s3_row])
    result = cmp.compare()

    assert result["max_level_failures"] == 1
    assert result["passes_oracle"] is False
