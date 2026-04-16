from __future__ import annotations

import pytest

from experiments.dynamic_experiment import (
    _advance_state,
    _derive_tool_calls_detail,
    _get_scenarios,
    run_static_baseline,
    run_dynamic_experiments,
    run_multi_round_dynamic_experiment,
)
from experiments.evaluation_metrics import evaluate_instruction_compliance
from experiments.paper_experiment_runner import summarize_all_results
from pyresops.agents import ReservoirToolBundleFactory


class StubExperiment:
    def __init__(self, outflows: dict[str, float]):
        self.outflows = outflows

    def run_scenario(self, scenario: dict) -> dict:
        stage = scenario.get("dynamic_stage", "baseline")
        outflow = self.outflows.get(stage, self.outflows.get("baseline", scenario["inflow"]))
        return {
            "scenario_id": scenario["id"],
            "outflow": outflow,
            "tool_call_count": 1,
            "tool_call_chain": ["simulate_dispatch_program"],
            "total_time_seconds": 0.01,
            "final_decision_text": f"Stage {stage}: recommend outflow {outflow} m3/s",
            "success": True,
        }


class StaticStubExperiment:
    def run_scenario(self, scenario: dict) -> dict:
        return {
            "scenario_id": scenario["id"],
            "outflow": 350.0,
            "tool_call_count": 2,
            "tool_call_chain": [
                "simulate_dispatch_program",
                "evaluate_dispatch_result",
            ],
            "tool_calls_detail": [
                {"call_order": 1, "tool_name": "simulate_dispatch_program"},
                {"call_order": 2, "tool_name": "evaluate_dispatch_result"},
            ],
            "llm_execution_trace": {
                "attempts": 1,
                "tool_events": [
                    {"attempt_index": 1, "call_order": 1, "tool_name": "simulate_dispatch_program"},
                    {"attempt_index": 1, "call_order": 2, "tool_name": "evaluate_dispatch_result"},
                ],
            },
            "accepted_attempt_index": 1,
            "acceptance_failure_reason": None,
            "accepted_evidence_pair": {
                "attempt_index": 1,
                "simulation": {
                    "attempt_index": 1,
                    "call_order": 1,
                    "tool_name": "simulate_dispatch_program",
                    "event_kind": "simulation",
                    "declared_outflow": 350.0,
                    "event_ok": True,
                    "failure_reason": None,
                    "result_payload": {
                        "scenario_id": scenario["id"],
                        "declared_outflow": 350.0,
                        "sim_final_level": 156.2,
                        "sim_max_level": 157.5,
                    },
                },
                "evaluation": {
                    "attempt_index": 1,
                    "call_order": 2,
                    "tool_name": "evaluate_dispatch_result",
                    "event_kind": "evaluation",
                    "declared_outflow": 350.0,
                    "event_ok": True,
                    "failure_reason": None,
                    "result_payload": {
                        "scenario_id": scenario["id"],
                        "declared_outflow": 350.0,
                        "overall_score": 0.91,
                        "flood_control_score": 0.95,
                        "water_supply_score": 0.81,
                        "power_generation_score": 0.72,
                        "ecological_score": 1.0,
                    },
                },
            },
            "total_time_seconds": 0.01,
            "final_decision_text": "ok",
            "success": True,
        }


def test_advance_state_reduces_level_for_s01() -> None:
    scenario = _get_scenarios()["S01"]

    state = _advance_state(scenario, 1200.0, 6)

    assert state["level"] < 157.5


def test_evaluate_instruction_compliance_handles_flow_limit_and_best_effort() -> None:
    state_before = {"level": 165.0, "storage": 39.0, "inflow": 12000.0, "outflow": 9000.0}
    safe_state_after = {"level": 168.5, "storage": 40.5, "inflow": 12000.0, "outflow": 5000.0}
    unsafe_state_after = {"level": 169.6, "storage": 41.0, "inflow": 12000.0, "outflow": 5000.0}

    flow_limit_trigger = {
        "pass_condition": {"type": "flow_limit", "max_flow": 400.0},
        "is_hard_task": False,
    }
    assert evaluate_instruction_compliance(
        flow_limit_trigger, 350.0, state_before, safe_state_after
    )["pass"]
    assert not evaluate_instruction_compliance(
        flow_limit_trigger, 5000.0, state_before, safe_state_after
    )["pass"]

    best_effort_trigger = {
        "pass_condition": {
            "type": "best_effort",
            "primary": {"type": "flow_limit", "max_flow": 8000.0},
            "safety_constraint": {"type": "level_max", "max_level": 169.15},
            "tolerance_multiplier": 2.0,
        },
        "is_hard_task": True,
    }
    result = evaluate_instruction_compliance(
        best_effort_trigger, 5000.0, state_before, safe_state_after
    )
    assert result["pass"] is True
    assert result["is_hard_task"] is True
    assert 0.0 <= result["partial_credit"] < 1.0
    assert not evaluate_instruction_compliance(
        best_effort_trigger, 5000.0, state_before, unsafe_state_after
    )["pass"]


def test_run_multi_round_dynamic_experiment_evolves_state() -> None:
    experiment = StubExperiment({"T0": 1200.0, "T1": 1500.0, "T2": 1800.0, "T3": 600.0})

    summary = run_multi_round_dynamic_experiment("S01", experiment=experiment, save_result=False)

    assert len(summary["stages"]) == 4
    assert summary["stages"][1]["state_before"]["level"] != 157.5
    assert (
        summary["stages"][2]["state_before"]["level"]
        != summary["stages"][1]["state_before"]["level"]
    )
    assert "overall_pass_rate" in summary


def test_run_dynamic_experiments_preserves_legacy_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyresops.agents as agents_module

    class FakeExperiment(StubExperiment):
        def __init__(self, *args, **kwargs):
            super().__init__({"baseline": 800.0, "T0": 350.0})

    monkeypatch.setattr(agents_module, "ReservoirAgentRuntime", FakeExperiment)

    results = run_dynamic_experiments(scenario_ids=["S02"])

    assert "adjustment_effective" in results[0]
    assert "constraint_achievement_rate" in results[0]
    assert "score_change" in results[0]
    assert "overall_pass_rate" in results[0]


def test_paper_runner_prefers_runtime_scenario_and_summarizes_pass_rate() -> None:
    factory = ReservoirToolBundleFactory(scenario_resolver=lambda _sid: None)
    runtime_scenario = {"id": "S01", "current_level": 155.0}
    resolved = factory.resolve_scenario_config("S01", runtime_scenario=runtime_scenario)

    assert resolved is runtime_scenario

    static_results = [
        {
            "llm_scores": {"overall": 0.8},
            "human_scores": {"overall": 0.7},
            "llm_constraint_violations": 0,
            "process_complete": True,
        }
    ]
    dynamic_results = [
        {
            "scenario_id": "S03",
            "overall_pass_rate": 0.75,
            "hard_task_partial_credits": {"T1": 0.62},
        }
    ]

    summary = summarize_all_results(static_results, dynamic_results)

    assert summary["dynamic_summary"]["overall_pass_rate"] == 0.75
    assert summary["dynamic_summary"]["per_scenario_pass_rates"]["S03"] == 0.75
    assert summary["dynamic_summary"]["hard_task_partial_credits"]["S03"] == {"T1": 0.62}


def test_tool_calls_detail_derives_from_trace_events() -> None:
    result = {
        "llm_execution_trace": {
            "tool_events": [
                {"call_order": 2, "tool_name": "evaluate_dispatch_result"},
                {"call_order": 3, "tool_name": "check_safety_constraints"},
            ]
        }
    }
    assert _derive_tool_calls_detail(result) == [
        {"call_order": 2, "tool_name": "evaluate_dispatch_result"},
        {"call_order": 3, "tool_name": "check_safety_constraints"},
    ]


def test_tool_calls_detail_falls_back_to_tool_call_chain() -> None:
    result = {
        "tool_call_chain": [
            "simulate_dispatch_program",
            "evaluate_dispatch_result",
        ]
    }
    assert _derive_tool_calls_detail(result) == [
        {"call_order": 1, "tool_name": "simulate_dispatch_program"},
        {"call_order": 2, "tool_name": "evaluate_dispatch_result"},
    ]


def test_canonical_trace_precedes_alias_when_both_exist() -> None:
    class MismatchStubExperiment:
        def run_scenario(self, scenario: dict) -> dict:
            return {
                "scenario_id": scenario["id"],
                "outflow": 350.0,
                "tool_call_count": 2,
                "tool_call_chain": [
                    "simulate_dispatch_program",
                    "evaluate_dispatch_result",
                ],
                "tool_calls_detail": [{"call_order": 1, "tool_name": "legacy_only"}],
                "llm_execution_trace": {
                    "attempts": 1,
                    "tool_events": [
                        {
                            "attempt_index": 1,
                            "call_order": 1,
                            "tool_name": "simulate_dispatch_program",
                        },
                        {
                            "attempt_index": 1,
                            "call_order": 2,
                            "tool_name": "evaluate_dispatch_result",
                        },
                    ],
                },
                "accepted_attempt_index": 1,
                "acceptance_failure_reason": None,
                "accepted_evidence_pair": {
                    "attempt_index": 1,
                    "simulation": {
                        "attempt_index": 1,
                        "call_order": 1,
                        "tool_name": "simulate_dispatch_program",
                        "event_kind": "simulation",
                        "declared_outflow": 350.0,
                        "event_ok": True,
                        "failure_reason": None,
                        "result_payload": {"declared_outflow": 350.0},
                    },
                    "evaluation": {
                        "attempt_index": 1,
                        "call_order": 2,
                        "tool_name": "evaluate_dispatch_result",
                        "event_kind": "evaluation",
                        "declared_outflow": 350.0,
                        "event_ok": True,
                        "failure_reason": None,
                        "result_payload": {"declared_outflow": 350.0, "overall_score": 0.9},
                    },
                },
                "total_time_seconds": 0.01,
                "final_decision_text": "ok",
                "success": True,
            }

    baseline = run_static_baseline("S01", experiment=MismatchStubExperiment(), save_result=False)
    assert baseline["tool_call_chain"] == [
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    assert baseline["tool_calls_detail"] == [{"call_order": 1, "tool_name": "legacy_only"}]


def test_static_baseline_uses_canonical_runner_fields() -> None:
    result = run_static_baseline("S01", experiment=StaticStubExperiment(), save_result=False)
    assert result["outflow"] == 350.0
    assert result["tool_call_chain"] == [
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]
    assert result["accepted_attempt_index"] == 1
    assert result["sim_details"]["simulation"]["declared_outflow"] == 350.0
    assert result["sim_details"]["evaluation"]["overall_score"] == 0.91


def test_static_baseline_enables_constrained_profile_for_s01() -> None:
    captured = {}

    class ProfileCaptureExperiment:
        def run_scenario(self, scenario):
            captured["profile"] = scenario.get("agent_workflow_profile")
            return {
                "outflow": float(scenario["inflow"]),
                "tool_call_count": 0,
                "tool_call_chain": [],
                "tool_calls_detail": [],
                "llm_execution_trace": {},
                "accepted_attempt_index": None,
                "acceptance_failure_reason": "missing_simulation",
                "accepted_evidence_pair": None,
                "total_time_seconds": 0.0,
                "final_decision_text": "",
                "success": False,
            }

    run_static_baseline("S01", experiment=ProfileCaptureExperiment(), save_result=False)
    assert captured["profile"] == "static_s01_mcp_chain_v1"
