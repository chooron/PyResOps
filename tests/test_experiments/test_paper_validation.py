from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from experiments.check_paper_validation_gates import evaluate_gates
from experiments.paper_validation.config import load_paper_validation_config
from experiments.paper_validation.mcp_audit import run_mcp_schema_audit
from experiments.paper_validation.mcp_skill_runner import (
    MCP_TRACE_DEFAULTS,
    _load_mcp_config,
    validate_skill_protocol,
)
from experiments.paper_validation.runners import METHOD_REGISTRY, registered_method_levels
from experiments.paper_validation.schema import validate_structured_payload


def test_paper_validation_config_loads() -> None:
    cfg = load_paper_validation_config()
    assert cfg["name"] == "paper_validation"
    assert "static_large" in cfg
    assert "dynamic_representative" in cfg
    assert "rolling_real_forecast" in cfg
    assert "rolling_stress" in cfg


def test_method_levels_registered() -> None:
    levels = registered_method_levels()
    assert levels == {
        "pyresops_direct": "L0",
        "tools_only": "L1",
        "mimo_without_tools": "L2",
        "mimo_with_pyresops_tools": "L3",
        "mimo_mcp_validator": "L4",
        "mimo_mcp_skill": "B4",
    }
    assert set(levels) == set(METHOD_REGISTRY)


def test_structured_payload_validation() -> None:
    valid, failure = validate_structured_payload(
        {
            "event_id": "E1",
            "workflow": "static",
            "stage_id": "static_initial",
            "method_level": "L3",
            "transport": "mcp_tools",
            "skill_name": "static_operation_skill",
            "decision_type": "accept",
            "selected_plan_id": "plan_1",
            "target_release_summary": {"target_release_m3s": 100.0},
            "safety_status": "safe",
            "hard_constraint_violation": False,
            "instruction_status": "satisfied",
            "tool_chain_summary": ["prepare_event"],
            "mcp_tool_chain_summary": ["prepare_event"],
            "evaluation_reference": "eval_1",
            "failure_reason": None,
            "explanation": "ok",
        }
    )
    invalid, invalid_failure = validate_structured_payload({"event_id": "E1"})

    assert failure is None
    assert valid is not None
    assert invalid is None
    assert invalid_failure == "invalid_final_payload"


def test_mcp_schema_audit(tmp_path) -> None:
    result = run_mcp_schema_audit(output_root=tmp_path)
    json_path = Path(result["json_path"])
    md_path = Path(result["markdown_path"])

    assert json_path.exists()
    assert md_path.exists()
    summary = json.loads(json_path.read_text(encoding="utf-8"))
    assert summary["core_tools_present"]["prepare_event"] is True
    assert summary["core_tools_present"]["run_static_workflow"] is True
    assert summary["core_tools_present"]["validate_decision_payload"] is True


def test_gate_checker_pass_fail(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    pd.DataFrame(
        [
            {
                "method_id": "tools_only",
                "paper_method_level": "L1",
                "workflow_type": "static",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": True,
                "forecast_error_type": None,
                "tool_call_chain": "[]",
            },
            {
                "method_id": "mimo_with_pyresops_tools",
                "paper_method_level": "L3",
                "workflow_type": "static",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": True,
                "forecast_error_type": None,
                "tool_call_chain": "['prepare_event']",
            },
            {
                "method_id": "mimo_with_pyresops_tools",
                "paper_method_level": "L3",
                "workflow_type": "dynamic",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": True,
                "protocol_adherent": True,
                "forecast_error_type": None,
                "tool_call_chain": "['get_reservoir_status', 'query_dispatch_rules', 'simulate_dispatch_program', 'evaluate_dispatch_result']",
            },
            {
                "method_id": "mimo_with_pyresops_tools",
                "paper_method_level": "L3",
                "workflow_type": "rolling",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": True,
                "forecast_error_type": "lag",
                "tool_call_chain": "['prepare_event']",
            },
            {
                "method_id": "mimo_mcp_validator",
                "paper_method_level": "L4",
                "workflow_type": "static",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": True,
                "forecast_error_type": None,
                "tool_call_chain": "['prepare_event']",
            },
            {
                "method_id": "mimo_mcp_validator",
                "paper_method_level": "L4",
                "workflow_type": "dynamic",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": True,
                "protocol_adherent": True,
                "forecast_error_type": None,
                "tool_call_chain": "['get_reservoir_status', 'query_dispatch_rules', 'simulate_dispatch_program', 'evaluate_dispatch_result']",
            },
            {
                "method_id": "mimo_mcp_validator",
                "paper_method_level": "L4",
                "workflow_type": "rolling",
                "process_success": True,
                "safety_status": "safe",
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": True,
                "forecast_error_type": "lag",
                "tool_call_chain": "['prepare_event']",
            },
        ]
    ).to_csv(summary_path, index=False, encoding="utf-8-sig")

    passed = evaluate_gates(summary_path)

    assert passed["status"] == "PASS"

    pd.DataFrame(
        [
            {
                "method_id": "tools_only",
                "paper_method_level": "L1",
                "workflow_type": "static",
                "process_success": False,
                "safety_status": "hard_constraint_violation",
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": False,
                "forecast_error_type": None,
                "tool_call_chain": "[]",
            }
        ]
    ).to_csv(summary_path, index=False, encoding="utf-8-sig")
    failed = evaluate_gates(summary_path)

    assert failed["status"] == "FAIL"
    assert failed["failed_gate_names"]


def test_dynamic_carry_over_rate(tmp_path) -> None:
    summary_path = tmp_path / "summary.csv"
    pd.DataFrame(
        [
                {
                    "method_id": "mimo_mcp_validator",
                    "paper_method_level": "L4",
                    "workflow_type": "dynamic",
                    "process_success": True,
                    "safety_status": "safe",
                    "event_class": "strict_clean",
                    "had_carry_over_plan": True,
                    "protocol_adherent": True,
                    "forecast_error_type": None,
                    "tool_call_chain": "['get_reservoir_status', 'query_dispatch_rules', 'simulate_dispatch_program', 'evaluate_dispatch_result']",
                },
                {
                    "method_id": "mimo_mcp_validator",
                    "paper_method_level": "L4",
                    "workflow_type": "dynamic",
                    "process_success": True,
                    "safety_status": "safe",
                    "event_class": "strict_clean",
                    "had_carry_over_plan": True,
                    "protocol_adherent": True,
                    "forecast_error_type": None,
                    "tool_call_chain": "['get_reservoir_status', 'query_dispatch_rules', 'simulate_dispatch_program', 'evaluate_dispatch_result']",
                },
        ]
    ).to_csv(summary_path, index=False, encoding="utf-8-sig")

    result = evaluate_gates(summary_path)
    assert result["metrics"]["mimo_dynamic_carry_over_evaluation_rate"] == 1.0


def test_static_protocol_taxonomy() -> None:
    from experiments.paper_validation.runners import _paper_protocol_failure

    payload = {"workflow_type": "static"}
    assert _paper_protocol_failure(payload, ["prepare_event", "optimize_release_plan", "optimize_release_plan"], None) == "repeated_static_optimization"
    assert _paper_protocol_failure(payload, ["prepare_event", "simulate_release_plan", "optimize_release_plan", "evaluate_release_plan"], None) == "wrong_tool_order"
    assert _paper_protocol_failure(payload, ["prepare_event", "simulate_release_plan", "evaluate_release_plan", "optimize_release_plan"], None) == "wrong_tool_order"


def test_mcp_skill_config_loads() -> None:
    cfg = load_paper_validation_config()
    assert "mcp" in cfg
    assert "mcp-skill-smoke" in cfg["phases"]
    assert "mcp-skill-static" in cfg["phases"]
    assert "mcp-skill-dynamic" in cfg["phases"]
    assert "mcp-skill-rolling" in cfg["phases"]


def test_skill_contract_files_exist() -> None:
    root = Path("experiments/paper_validation/skills")
    expected = [
        "common_safety_skill.md",
        "static_operation_skill.md",
        "dynamic_operation_skill.md",
        "rolling_operation_skill.md",
    ]
    for name in expected:
        path = root / name
        assert path.exists()
        assert path.read_text(encoding="utf-8").strip()


def test_mcp_tools_runner_requires_mcp_transport() -> None:
    try:
        _load_mcp_config({"mcp": {"transport": "streamable-http", "url": None, "command": None}})
    except ValueError as exc:
        assert "mcp.url" in str(exc)
    else:
        raise AssertionError("HTTP MCP transport without url must fail")


def test_mcp_trace_fields_present() -> None:
    required = [
        "transport",
        "skill_enabled",
        "skill_name",
        "mcp_transport",
        "mcp_connect_success",
        "mcp_tools_list_success",
        "mcp_available_tool_names",
        "mcp_tool_call_sequence",
        "mcp_tool_call_count",
        "mcp_tool_call_success_count",
        "mcp_tool_call_failure_count",
        "mcp_structured_result_count",
        "mcp_unstructured_result_count",
        "mcp_error_message",
        "final_payload_valid",
        "final_payload_validation_error",
        "protocol_adherence",
    ]
    for field in required:
        assert field in MCP_TRACE_DEFAULTS


def test_static_skill_protocol_validation() -> None:
    payload = {"workflow_type": "static"}
    assert validate_skill_protocol(workflow="static", tool_chain=["prepare_event"], final_payload={}, stage_payload=payload) == "missing_required_tool"
    assert validate_skill_protocol(
        workflow="static",
        tool_chain=["prepare_event", "optimize_release_plan", "optimize_release_plan"],
        final_payload={},
        stage_payload=payload,
    ) == "repeated_static_optimization"
    assert validate_skill_protocol(
        workflow="static",
        tool_chain=["prepare_event", "optimize_release_plan", "simulate_release_plan"],
        final_payload={},
        stage_payload=payload,
    ) == "missing_required_tool"


def test_dynamic_skill_carry_over_validation() -> None:
    assert validate_skill_protocol(
        workflow="dynamic",
        tool_chain=["optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"],
        final_payload={},
        stage_payload={"carry_over_plan": {"outflow": 100.0}},
    ) == "missing_carry_over_evaluation"


def test_rolling_skill_trigger_validation() -> None:
    assert validate_skill_protocol(
        workflow="rolling",
        tool_chain=["optimize_release_plan", "simulate_release_plan", "evaluate_release_plan"],
        final_payload={},
        stage_payload={},
    ) == "missing_rolling_trigger_reason"


def test_mcp_gate_checker(tmp_path) -> None:
    summary_path = tmp_path / "mcp_summary.csv"
    pd.DataFrame(
        [
            {
                "phase": "mcp-skill-smoke",
                "method_id": "mimo_mcp_skill",
                "paper_method_level": "B4",
                "workflow_type": "static",
                "process_success": True,
                "safety_status": "safe",
                "hard_constraint_violation": False,
                "event_class": "strict_clean",
                "had_carry_over_plan": False,
                "protocol_adherent": True,
                "structured_output_valid": True,
                "forecast_error_type": None,
                "tool_call_chain": "['prepare_event','optimize_release_plan','simulate_release_plan','evaluate_release_plan']",
                "transport": "mcp_tools",
                "mcp_connect_success": True,
                "mcp_tools_list_success": True,
                "mcp_tool_call_count": 4,
                "mcp_tool_call_success_count": 4,
                "mcp_tool_call_sequence": "['prepare_event','optimize_release_plan','simulate_release_plan','evaluate_release_plan']",
                "final_payload_valid": True,
                "trigger_reason": "known_full_real_hydrograph",
            }
        ]
    ).to_csv(summary_path, index=False, encoding="utf-8-sig")
    result = evaluate_gates(summary_path, include_mcp_skill=True)
    assert result["status"] == "PASS"
