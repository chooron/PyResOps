from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from experiments.check_paper_validation_gates import evaluate_gates
from experiments.paper_validation.config import load_paper_validation_config, load_phase_config
from experiments.paper_validation.command_challenge import (
    build_payload_repair_audit_rows,
    command_challenge_gate_metrics,
    enrich_record_with_command_metrics,
    export_cross_model_tables,
    load_command_challenge_config,
)
from experiments.paper_validation.mcp_audit import run_mcp_schema_audit
from experiments.paper_validation.mcp_skill_runner import (
    MCP_TRACE_DEFAULTS,
    _compact_scenario_for_llm,
    _context_key,
    _load_no_skill_instructions,
    _load_mcp_config,
    _mcp_payload_failure,
    collect_available_evaluation_references,
    validate_skill_protocol,
)
import experiments.paper_validation.orchestrator as orchestrator
from experiments.paper_validation.orchestrator import load_targeted_rerun_failures, run_paper_validation_phase
from experiments.paper_validation.runners import METHOD_REGISTRY, registered_method_levels
from experiments.paper_validation.schema import validate_structured_payload
from experiments.paper_validation.tooling import _normalize_mcp_scenario
from experiments.run_cross_model_phase_g import PhaseRunResult, aggregate_cross_model_results
from experiments.validation.results import compact_audit_payload, compact_stage_result
from pyresops.agents.config_loader import AgentModelConfigLoader


def test_paper_validation_config_loads() -> None:
    cfg = load_paper_validation_config()
    assert cfg["name"] == "paper_validation"
    assert "static_large" in cfg
    assert "dynamic_representative" in cfg
    assert "rolling_real_forecast" in cfg
    assert "rolling_stress" in cfg
    rolling = cfg["rolling_real_forecast"]
    assert len(rolling["rolling_event_paths"]) == 10
    assert rolling["check_interval_hours"] == 12
    assert rolling["scheduled_check_replan"] is True
    assert rolling["continue_on_stage_failure"] is True
    assert rolling["manual_instruction_offsets"] == {}


def test_method_levels_registered() -> None:
    levels = registered_method_levels()
    assert levels == {
        "pyresops_direct": "L0",
        "tools_only": "L1",
        "mimo_without_tools": "L2",
        "mimo_with_pyresops_tools": "L3",
        "mimo_mcp_no_skill": "B3",
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
    assert "freeze-mcp-skill-v1" in cfg["phases"]
    assert "component-ablation" in cfg["phases"]


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


def test_mcp_no_skill_instructions_do_not_load_skill_contract() -> None:
    instructions = _load_no_skill_instructions("B3")
    assert "No workflow skill contract is provided" in instructions
    assert "Static workflow required chain" not in instructions
    assert "Dynamic workflow required protocol" not in instructions
    assert "Rolling workflow protocol" not in instructions


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


def test_mcp_prompt_uses_hydratable_compact_scenario() -> None:
    payload = {
        "id": "static_2010062002",
        "workflow_type": "static",
        "data_source": {
            "path": "data/processed/flood_event/2010062002.csv",
            "event_id": "2010062002",
            "uses_processed_data": True,
        },
        "start_time": "2010-06-16T11:00:00",
        "current_level": 154.37,
        "target_level": 154.37,
        "target_level_tolerance": 0.5,
        "stage_offset_hours": 0,
        "operator_instruction": "",
        "benchmark_inflow_series_m3s": [118.0, 118.0],
        "benchmark_observed_outflow_series_m3s": [0.0, 0.0],
        "benchmark_precipitation_series_mm": [0.2, 0.5],
    }
    compact = _compact_scenario_for_llm(payload)
    assert "benchmark_inflow_series_m3s" not in compact
    assert compact["series_hydration"]["series_length"] == 2

    hydrated = _normalize_mcp_scenario(compact)
    assert hydrated["id"] == "static_2010062002"
    assert len(hydrated["benchmark_inflow_series_m3s"]) > 2
    assert hydrated["benchmark_inflow_series_m3s"][0] == 118.0


def test_mcp_context_key_separates_events_but_keeps_dynamic_stages() -> None:
    first = {
        "id": "dynamic_2010062002_0h",
        "workflow_type": "dynamic",
        "data_source": {"event_id": "2010062002"},
    }
    second = {
        "id": "dynamic_2010062002_3h",
        "workflow_type": "dynamic",
        "data_source": {"event_id": "2010062002"},
    }
    other_event = {
        "id": "dynamic_2020070914_0h",
        "workflow_type": "dynamic",
        "data_source": {"event_id": "2020070914"},
    }
    static_case_a = {
        "id": "static_2010062002",
        "workflow_type": "static",
        "data_source": {"event_id": "2010062002"},
        "command_id": "c1",
    }
    static_case_b = {
        "id": "static_2010062002",
        "workflow_type": "static",
        "data_source": {"event_id": "2010062002"},
        "command_id": "c2",
    }

    assert _context_key(first) == _context_key(second)
    assert _context_key(first) != _context_key(other_event)
    assert _context_key(static_case_a) != _context_key(static_case_b)
    assert _context_key(first)[1] == "event"
    assert _context_key(static_case_a)[1] == "scenario"


def test_audit_payload_compacts_long_mcp_context() -> None:
    payload = {
        "llm_execution_trace": {
            "user_message": "x" * 9000,
            "tool_events": [
                {
                    "tool_name": "optimize_release_plan",
                    "tool_args": {
                        "scenario": {
                            "benchmark_inflow_series_m3s": list(range(100)),
                        }
                    },
                    "result": json.dumps(
                        {
                            "release_values_m3s": list(range(80)),
                            "family_attempts": [
                                {
                                    "module_type": "constant_release",
                                    "candidate_count": 30,
                                    "solver_method": "test",
                                    "selected_candidate": {
                                        "feasible": True,
                                        "final_level_m": 154.0,
                                        "avg_outflow_m3s": 900.0,
                                        "unmet_task_constraints": [],
                                    },
                                }
                            ],
                        }
                    ),
                }
            ],
        }
    }
    compact = compact_audit_payload(payload)
    scenario = compact["llm_execution_trace"]["tool_events"][0]["tool_args"]["scenario"]
    assert scenario["benchmark_inflow_series_m3s"]["count"] == 100
    assert scenario["benchmark_inflow_series_m3s"]["truncated"] is True
    assert compact["llm_execution_trace"]["user_message"]["truncated"] is True
    decoded_result = json.loads(compact["llm_execution_trace"]["tool_events"][0]["result"])
    assert decoded_result["release_values_m3s"]["count"] == 80
    assert decoded_result["family_attempts"]["count"] == 1

    compact_result = compact_stage_result(payload)
    assert "tool_events" not in compact_result["llm_execution_trace"]
    assert compact_result["llm_execution_trace"]["tool_events_summary"]["sequence"] == [
        "optimize_release_plan"
    ]


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


def test_component_ablation_gate_checker(tmp_path) -> None:
    summary_path = tmp_path / "component_summary.csv"
    rows = [
        {
            "phase": "component-ablation",
            "method_id": "mimo_without_tools",
            "paper_method_level": "L2",
            "workflow_type": "static",
            "process_success": False,
            "failure_reason": "invalid_final_payload",
            "safety_status": "unknown",
            "hard_constraint_violation": False,
            "event_class": "strict_clean",
            "had_carry_over_plan": False,
            "protocol_adherent": False,
            "structured_output_valid": False,
            "forecast_error_type": None,
            "tool_call_chain": "[]",
            "executable_plan": False,
            "evaluation_reference_valid": False,
        },
        {
            "phase": "component-ablation",
            "method_id": "mimo_mcp_no_skill",
            "paper_method_level": "B3",
            "workflow_type": "static",
            "process_success": True,
            "failure_reason": "",
            "safety_status": "safe",
            "hard_constraint_violation": False,
            "event_class": "strict_clean",
            "had_carry_over_plan": False,
            "protocol_adherent": False,
            "structured_output_valid": True,
            "forecast_error_type": None,
            "tool_call_chain": "['prepare_event','optimize_release_plan','simulate_release_plan','evaluate_release_plan']",
            "transport": "mcp_tools",
            "mcp_connect_success": True,
            "mcp_tools_list_success": True,
            "mcp_tool_call_count": 4,
            "mcp_tool_call_success_count": 4,
            "mcp_tool_call_sequence": "['prepare_event','optimize_release_plan','simulate_release_plan','evaluate_release_plan']",
            "executable_plan": True,
            "evaluation_reference_valid": True,
        },
        {
            "phase": "component-ablation",
            "method_id": "mimo_mcp_skill",
            "paper_method_level": "B4",
            "workflow_type": "static",
            "process_success": True,
            "failure_reason": "",
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
            "executable_plan": True,
            "evaluation_reference_valid": True,
        },
    ]
    pd.DataFrame(rows).to_csv(summary_path, index=False, encoding="utf-8-sig")
    result = evaluate_gates(summary_path, include_component_ablation=True)
    assert result["status"] == "PASS"


def test_command_challenge_config_loads() -> None:
    cfg = load_command_challenge_config()
    cases = []
    for section in ("static_cases", "dynamic_cases", "rolling_cases"):
        cases.extend(cfg[section])
    assert len({case["command_type"] for case in cases}) >= 8
    for case in cases:
        assert case["command_id"]
        assert case["command_type"]
        assert case["workflow"] in {"static", "dynamic", "rolling"}
        assert case["expected_instruction_status"]


def test_command_challenge_metrics() -> None:
    frame = pd.DataFrame(
        [
            {
                "phase": "command-challenge",
                "paper_method_level": "B4",
                "command_id": "c1",
                "command_type": "C1_normal_lower_target_level",
                "process_success": True,
                "hard_constraint_violation": False,
                "structured_output_valid": True,
                "protocol_adherent": True,
                "evaluation_reference_valid": True,
                "command_following_success": True,
                "is_infeasible_command": False,
                "infeasible_command_detected": False,
                "is_unsafe_command": False,
                "unsafe_command_rejected": False,
            },
            {
                "phase": "command-challenge",
                "paper_method_level": "B4",
                "command_id": "c7",
                "command_type": "C7_physically_infeasible_instruction",
                "process_success": True,
                "hard_constraint_violation": False,
                "structured_output_valid": True,
                "protocol_adherent": True,
                "evaluation_reference_valid": True,
                "command_following_success": True,
                "is_infeasible_command": True,
                "infeasible_command_detected": True,
                "is_unsafe_command": False,
                "unsafe_command_rejected": False,
            },
            {
                "phase": "command-challenge",
                "paper_method_level": "B4",
                "command_id": "c6",
                "command_type": "C6_conflicting_safety_instruction",
                "process_success": True,
                "hard_constraint_violation": False,
                "structured_output_valid": True,
                "protocol_adherent": True,
                "evaluation_reference_valid": True,
                "command_following_success": True,
                "is_infeasible_command": False,
                "infeasible_command_detected": False,
                "is_unsafe_command": True,
                "unsafe_command_rejected": True,
            },
        ]
    )
    metrics = command_challenge_gate_metrics(frame)
    assert metrics["command_b4_command_following_success_rate"] == 1.0
    assert metrics["command_b4_infeasible_command_detection_rate"] == 1.0
    assert metrics["command_b4_unsafe_command_rejection_rate"] == 1.0


def test_safe_rejection_is_success_for_infeasible_command() -> None:
    record = {
        "structured_output_valid": True,
        "protocol_adherent": True,
        "evaluation_reference_valid": True,
        "hard_constraint_violation": False,
        "final_payload": {
            "decision_type": "reject_infeasible",
            "instruction_status": "infeasible",
            "evaluation_reference": "evaluate_release_plan::x",
        },
        "failure_reason": None,
    }
    enrich_record_with_command_metrics(
        record,
        {
            "command_id": "c7",
            "command_type": "C7_physically_infeasible_instruction",
            "expected_instruction_status": "infeasible",
            "expected_safe_rejection": True,
            "requires_replan": False,
        },
    )
    assert record["command_following_success"] is True
    assert record["infeasible_command_detected"] is True
    assert record["process_success"] is True


def test_deepseek_profile_loads(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    pro = AgentModelConfigLoader().load(profile="deepseek_v4_pro", config_path="experiments/config/llm_config.yml")
    flash = AgentModelConfigLoader().load(profile="deepseek_v4_flash", config_path="experiments/config/llm_config.yml")
    assert pro["model_id"] == "deepseek-v4-pro"
    assert flash["model_id"] == "deepseek-v4-flash"
    assert pro["base_url"] == "https://api.deepseek.com"


def test_low_cost_cross_model_profiles_load(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("MINMAX_API_KEY", "test-minimax")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-qwen")
    monkeypatch.delenv("GEMINI_BASE_URL", raising=False)
    monkeypatch.delenv("MINMAX_BASE_URL", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    gemini = AgentModelConfigLoader().load(
        profile="gemini_3_1_flash_lite",
        config_path="experiments/config/llm_config.yml",
    )
    minimax = AgentModelConfigLoader().load(
        profile="minimax_m2_5_free",
        config_path="experiments/config/llm_config.yml",
    )
    qwen = AgentModelConfigLoader().load(
        profile="qwen3_6_flash",
        config_path="experiments/config/llm_config.yml",
    )
    assert gemini["model_id"] == "gemini-3.1-flash-lite"
    assert gemini["provider"] == "gemini_native"
    assert "base_url" not in gemini
    assert minimax["model_id"] == "MiniMax-M2.5"
    assert minimax["base_url"] == "https://api.penguinsaichat.dpdns.org/v1"
    assert qwen["model_id"] == "qwen3.6-flash"
    assert qwen["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_cross_model_phase_config_loads() -> None:
    cfg = load_paper_validation_config()
    phase = load_phase_config(cfg, "cross-model-mcp-skill-subset")
    assert phase.methods == ("mimo_mcp_skill",)
    assert "command_challenge" in phase.scenario_groups
    assert "deepseek_static_subset" in phase.scenario_groups


def test_deepseek_missing_api_key_error(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(AgentModelConfigLoader, "_load_env_file", classmethod(lambda cls: None))
    try:
        AgentModelConfigLoader().load(profile="deepseek_v4_pro", config_path="experiments/config/llm_config.yml")
    except ValueError as exc:
        assert "DEEPSEEK_API_KEY" in str(exc)
        assert "MiMo" not in str(exc)
    else:
        raise AssertionError("DeepSeek profile without key must fail")


def test_cross_model_subset_summary_generation(tmp_path) -> None:
    frame = pd.DataFrame(
        [
            {
                "phase": "deepseek-mcp-skill-subset",
                "model_profile": "deepseek_v4_pro",
                "paper_method_level": "B4",
                "workflow_type": "static",
                "process_success": True,
                "hard_constraint_violation": False,
                "mcp_tool_call_count": 4,
                "mcp_tool_call_success_count": 4,
                "structured_output_valid": True,
                "protocol_adherent": True,
            }
        ]
    )
    export_cross_model_tables(frame, tmp_path)
    output = tmp_path / "cross_model_subset_summary.csv"
    assert output.exists()
    rows = pd.read_csv(output, encoding="utf-8-sig")
    assert rows.iloc[0]["model_profile"] == "deepseek_v4_pro"
    assert rows.iloc[0]["success_rate"] == 1.0


def test_cross_model_phase_g_aggregation(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "full" / "deepseek_v4_flash"
    run_dir.mkdir(parents=True)
    jsonl = run_dir / "cross-model-mcp-skill-subset_20260511_000000_000000.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "run_id": jsonl.stem,
                "phase": "cross-model-mcp-skill-subset",
                "model_profile": "deepseek_v4_flash",
                "paper_method_level": "B4",
                "workflow_type": "static",
                "event_id": "e1",
                "process_success": True,
                "hard_constraint_violation": False,
                "mcp_tool_call_count": 4,
                "mcp_tool_call_success_count": 4,
                "structured_output_valid": True,
                "protocol_adherent": True,
                "command_id": None,
                "llm_usage": "RunMetrics(input_tokens=10, output_tokens=5, total_tokens=15)",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    paths = aggregate_cross_model_results(
        full_results=[
            PhaseRunResult(
                profile="deepseek_v4_flash",
                mode="full",
                output_dir=run_dir,
                command=["python"],
                returncode=0,
                stdout_tail="",
                stderr_tail="",
                run_id=jsonl.stem,
                jsonl_path=jsonl,
                records=1,
                smoke_passed=True,
                status="completed",
            )
        ],
        report_root=tmp_path / "paper_validation",
    )
    assert paths["summary_csv"].exists()
    assert paths["token_usage_csv"].exists()
    summary = pd.read_csv(paths["summary_csv"], encoding="utf-8-sig")
    assert "deepseek_v4_flash" in set(summary["model_profile"])
    tokens = pd.read_csv(paths["token_usage_csv"], encoding="utf-8-sig")
    assert int(tokens.iloc[0]["total_tokens_total"]) == 15


def test_payload_repair_audit() -> None:
    rows = build_payload_repair_audit_rows(
        [
            {
                "run_id": "r1",
                "paper_method_level": "B4",
                "model_profile": "mimo_v25",
                "workflow_type": "static",
                "event_id": "e1",
                "command_id": "c1",
                "final_payload_valid": False,
                "structured_output_valid": False,
                "final_payload": {"event_id": "e1"},
                "failure_reason": "invalid_final_payload",
                "raw_result": {"final_decision_text": '{"event_id":"e1"}', "tool_events": [{"tool_name": "evaluate_release_plan"}]},
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["original_valid"] is False
    assert rows[0]["repair_attempted"] is True
    assert rows[0]["repair_did_not_call_tools"] is True
    assert rows[0]["final_status_after_repair"] == "valid_after_repair"


def _sample_stage_payload() -> dict:
    return {
        "id": "rolling_2012062402_48h",
        "stage_id": "rolling_48h",
        "stage_offset_hours": 48,
        "workflow_type": "rolling",
        "data_source": {"event_id": "2012062402"},
    }


def _sample_decision_payload(evaluation_reference: str | None) -> dict:
    return {
        "event_id": "2012062402",
        "workflow": "rolling",
        "stage_id": "rolling_48h",
        "method_level": "L4",
        "transport": "mcp_tools",
        "skill_name": "rolling_operation_skill",
        "decision_type": "replan",
        "selected_plan_id": "plan_1",
        "target_release_summary": {"target_release_m3s": 100.0},
        "safety_status": "safe",
        "hard_constraint_violation": False,
        "instruction_status": "satisfied",
        "tool_chain_summary": ["evaluate_release_plan"],
        "mcp_tool_chain_summary": ["evaluate_release_plan"],
        "evaluation_reference": evaluation_reference,
        "failure_reason": None,
        "explanation": "ok",
    }


def test_available_evaluation_references_collected() -> None:
    references = collect_available_evaluation_references(
        [
            {
                "tool_name": "evaluate_release_plan",
                "result": {
                    "scenario_id": "rolling_2012062402_48h",
                    "program_id": "plan_1",
                    "safety_status": "safe",
                    "hard_constraint_violations_count": 0,
                },
            }
        ],
        _sample_stage_payload(),
    )

    assert references == [
        {
            "reference_id": "evaluate_release_plan::rolling_2012062402_48h",
            "tool_name": "evaluate_release_plan",
            "event_id": "2012062402",
            "stage_id": "rolling_48h",
            "offset_hours": 48,
            "plan_id": "plan_1",
            "safety_status": "safe",
            "hard_constraint_violation": False,
            "source": "tool_result",
        }
    ]


def test_final_payload_reference_must_match_available_list() -> None:
    decision, schema_failure = validate_structured_payload(_sample_decision_payload("made_up_reference"))
    references = [
        {
            "reference_id": "evaluate_release_plan::rolling_2012062402_48h",
            "tool_name": "evaluate_release_plan",
        }
    ]

    failure = _mcp_payload_failure(
        decision,
        schema_failure,
        ["evaluate_release_plan"],
        available_references=references,
    )

    assert failure == "hallucinated_evaluation_reference"


def test_missing_evaluation_reference_detected() -> None:
    decision, schema_failure = validate_structured_payload(_sample_decision_payload(None))

    failure = _mcp_payload_failure(
        decision,
        schema_failure,
        ["evaluate_release_plan"],
        available_references=[{"reference_id": "evaluate_release_plan::rolling_2012062402_48h"}],
    )

    assert failure == "missing_evaluation_reference"


def test_missing_evaluation_tool_result_detected() -> None:
    decision, schema_failure = validate_structured_payload(
        _sample_decision_payload("evaluate_release_plan::rolling_2012062402_48h")
    )

    failure = _mcp_payload_failure(
        decision,
        schema_failure,
        ["optimize_release_plan"],
        available_references=[],
    )

    assert failure in {"missing_required_tool", "missing_evaluation_tool_result"}


def test_targeted_rerun_loads_failure_audit(tmp_path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    run_id = "mimo-rolling_20260512_082639_713975"
    pd.DataFrame(
        [
            {
                "workflow_type": "rolling",
                "event_id": item["event_id"],
                "stage_id": item["stage_id"],
                "stage_offset_hours": item["stage_offset_hours"],
                "trigger_reason": item["trigger_reason"],
                "failure_reason": item["failure_reason"],
                "failure_taxonomy": item["failure_taxonomy"],
            }
            for item in orchestrator.ROLLING_TARGETED_RERUN_FALLBACK_FAILURES
        ]
    ).to_csv(source_dir / f"{run_id}_failure_audit.csv", index=False, encoding="utf-8-sig")

    failures = load_targeted_rerun_failures(source_run_id=run_id, source_dir=source_dir)

    assert len(failures) == 6
    assert {item["stage_id"] for item in failures} == {
        "rolling_24h",
        "rolling_36h",
        "rolling_48h",
        "rolling_72h",
        "rolling_168h",
        "rolling_204h",
    }


def test_targeted_rerun_does_not_overwrite_original_results(tmp_path, monkeypatch) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "targeted"
    source_dir.mkdir()
    run_id = "mimo-rolling_20260512_082639_713975"
    original_jsonl = source_dir / f"{run_id}.jsonl"
    original_jsonl.write_text('{"original": true}\n', encoding="utf-8")
    original_content = original_jsonl.read_text(encoding="utf-8")
    pd.DataFrame(
        [
            {
                "workflow_type": "rolling",
                "event_id": "2012062402",
                "stage_id": "rolling_48h",
                "stage_offset_hours": 48,
                "trigger_reason": "scheduled_12h_check",
                "failure_reason": "missing_evaluation_reference",
                "failure_taxonomy": "tool",
            }
        ]
    ).to_csv(source_dir / f"{run_id}_failure_audit.csv", index=False, encoding="utf-8-sig")

    def fake_run_cases(**kwargs):
        return [
            {
                "run_id": kwargs["jsonl_path"].stem,
                "event_id": "2012062402",
                "stage_id": "rolling_48h",
                "workflow_type": "rolling",
                "process_success": True,
                "failure_reason": None,
                "failure_taxonomy": None,
                "hard_constraint_violation": False,
                "available_evaluation_reference_count": 1,
                "final_evaluation_reference": "evaluate_release_plan::rolling_2012062402_48h",
                "reference_valid": True,
                "protocol_repair_attempted": False,
                "protocol_repair_success": False,
            }
        ]

    def fake_export_summary(**kwargs):
        return {"run_count": 1, "success_count": 1, "success_rate": 1.0}

    monkeypatch.setattr(orchestrator, "_run_cases", fake_run_cases)
    monkeypatch.setattr(orchestrator, "export_paper_summary", fake_export_summary)

    result = run_paper_validation_phase(
        phase="rolling-targeted-rerun",
        model_profile="mimo_v25",
        llm_config="experiments/config/llm_config.yml",
        source_run_id=run_id,
        source_dir=source_dir,
        output_dir=output_dir,
    )

    assert original_jsonl.read_text(encoding="utf-8") == original_content
    assert output_dir in Path(result["paths"]["jsonl"]).parents
    assert (output_dir / "rolling_targeted_rerun_comparison.csv").exists()
