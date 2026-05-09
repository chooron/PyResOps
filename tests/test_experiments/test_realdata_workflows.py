from __future__ import annotations

import pytest

from experiments.data_adapters import RealEventDataAdapter
from experiments.validation.deterministic import DeterministicToolRunner
from experiments.workflows import (
    DynamicRealDataWorkflow,
    RollingRealDataWorkflow,
    StaticRealDataWorkflow,
)
from experiments.workflows.contracts import STATIC_S01_CHAIN
import builtins

from pyresops.agents.model_builder import build_agno_model
from pyresops.agents.prompts import ReservoirPromptPack
from pyresops.agents.runner import ReservoirAgentRunner


def test_all_repository_flood_events_load_with_uniform_time_step() -> None:
    adapter = RealEventDataAdapter()

    events = adapter.load_all_flood_events()

    assert len(events) == 41
    assert {event.time_step_hours for event in events} == {3}
    assert all(event.records for event in events)


def test_outflow_fallback_uses_inflow_and_marks_stage_as_repaired_only() -> None:
    adapter = RealEventDataAdapter(
        quality_manifest_path="tests/nonexistent_event_quality_manifest.csv"
    )
    event = adapter.load_event("2009080920", prefer_processed=False)

    payload = adapter.to_payload(event, workflow_type="static")

    assert payload["initial_outflow"] == pytest.approx(payload["initial_inflow"])
    assert payload["benchmark_observed_outflow_series_m3s"][0] == pytest.approx(
        payload["benchmark_inflow_series_m3s"][0]
    )
    assert payload["data_source"]["outflow_fallback_applied"] is True
    assert payload["data_source"]["strict_clean_eligible"] is False
    assert payload["data_source"]["repaired_executable_eligible"] is True


def test_predicted_real_event_contains_predict_and_3h_step() -> None:
    adapter = RealEventDataAdapter()

    event = adapter.load_predicted_event()

    assert event.event_id == "2024072617_with_pred"
    assert event.has_prediction is True
    assert event.time_step_hours == 3
    assert any(record.predict is not None for record in event.records)


def test_static_s01_contract_uses_strict_five_tool_chain() -> None:
    adapter = RealEventDataAdapter()
    event = adapter.load_event("2024072617")

    prepared = StaticRealDataWorkflow(adapter).prepare(event)

    assert prepared.success is True
    assert prepared.contract.tool_chain == STATIC_S01_CHAIN
    assert prepared.stages[0].payload["agent_workflow_profile"] == (
        ReservoirPromptPack.STATIC_S01_CHAIN_PROFILE
    )
    assert prepared.stages[0].payload["data_source"]["uses_synthetic_data"] is False
    assert prepared.stages[0].payload["benchmark_inflow_series_m3s"][0] == pytest.approx(32.6)


def test_dynamic_workflow_builds_3h_6h_9h_real_state_stages() -> None:
    adapter = RealEventDataAdapter()
    event = adapter.load_event("2024072617")

    prepared = DynamicRealDataWorkflow(adapter).prepare(event)

    assert prepared.success is True
    assert [stage.offset_hours for stage in prepared.stages] == [3, 6, 9]
    assert all(stage.payload["workflow_type"] == "dynamic" for stage in prepared.stages)
    assert prepared.stages[0].payload["initial_inflow"] == pytest.approx(29.6)
    assert prepared.stages[1].payload["initial_inflow"] == pytest.approx(110.3)
    assert prepared.stages[2].payload["initial_inflow"] == pytest.approx(168.1)


def test_dynamic_instruction_unfinished_is_not_process_failure() -> None:
    scenario = {
        "agent_workflow_profile": ReservoirPromptPack.DYNAMIC_RESERVOIR_PROFILE,
        "current_level": 157.0,
        "target_level": 156.5,
        "target_level_tolerance": 0.1,
        "carry_over_plan": {"outflow": 100.0},
    }
    repeated_replan_chain = [
        "get_reservoir_status",
        "query_dispatch_rules",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
        "optimize_release_plan",
        "optimize_release_plan",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    ]

    failure = ReservoirAgentRunner._validate_profile_chain(
        scenario=scenario,
        tool_chain=repeated_replan_chain,
        payload={"outflow": 300.0},
    )
    warning = ReservoirAgentRunner._dynamic_protocol_warning(
        scenario=scenario,
        tool_chain=repeated_replan_chain,
    )
    instruction_status = ReservoirAgentRunner._derive_instruction_status(
        scenario=scenario,
        evaluation_payload={
            "final_level_m": 156.8,
            "target_level_m": 156.5,
            "instruction_violations_count": 1,
            "instruction_violations": [{"constraint_id": "target_level"}],
        },
    )

    assert failure is None
    assert warning == "repeated_dynamic_optimization"
    assert instruction_status["status"] == "in_progress"
    assert instruction_status["process_failure"] is False


def test_static_validator_distinguishes_repeated_and_wrong_order_failures() -> None:
    repeated_failure = ReservoirAgentRunner._validate_profile_chain(
        scenario={"agent_workflow_profile": ReservoirPromptPack.STATIC_RESERVOIR_PROFILE},
        tool_chain=[
            "get_reservoir_status",
            "query_dispatch_rules",
            "optimize_release_plan",
            "optimize_release_plan",
            "simulate_dispatch_program",
            "evaluate_dispatch_result",
        ],
        payload={"outflow": 300.0},
    )
    ordering_failure = ReservoirAgentRunner._validate_profile_chain(
        scenario={"agent_workflow_profile": ReservoirPromptPack.STATIC_RESERVOIR_PROFILE},
        tool_chain=[
            "get_reservoir_status",
            "query_dispatch_rules",
            "simulate_dispatch_program",
            "optimize_release_plan",
            "evaluate_dispatch_result",
        ],
        payload={"outflow": 300.0},
    )

    assert repeated_failure == "repeated_static_optimization"
    assert ordering_failure == "wrong_tool_order"


def test_static_validator_allows_zero_outflow_when_reported() -> None:
    failure = ReservoirAgentRunner._validate_profile_chain(
        scenario={"agent_workflow_profile": ReservoirPromptPack.STATIC_RESERVOIR_PROFILE},
        tool_chain=[
            "get_reservoir_status",
            "query_dispatch_rules",
            "optimize_release_plan",
            "simulate_dispatch_program",
            "evaluate_dispatch_result",
        ],
        payload={"outflow": 0.0},
    )

    assert failure is None


def test_dynamic_carry_over_must_be_evaluated_before_replan() -> None:
    scenario = {
        "agent_workflow_profile": ReservoirPromptPack.DYNAMIC_RESERVOIR_PROFILE,
        "carry_over_plan": {"outflow": 100.0},
    }

    failure = ReservoirAgentRunner._validate_profile_chain(
        scenario=scenario,
        tool_chain=[
            "get_reservoir_status",
            "query_dispatch_rules",
            "optimize_release_plan",
            "simulate_dispatch_program",
            "evaluate_dispatch_result",
        ],
        payload={"outflow": 300.0},
    )

    assert failure == "missing_carry_over_evaluation"


def test_rolling_workflow_uses_predict_and_records_replan_reasons() -> None:
    adapter = RealEventDataAdapter()
    event = adapter.load_predicted_event()

    prepared = RollingRealDataWorkflow(adapter).prepare(event)

    assert prepared.success is True
    assert prepared.stages
    assert all("benchmark_predicted_inflow_series_m3s" in stage.payload for stage in prepared.stages)
    assert "manual_instruction" in {stage.replan_reason for stage in prepared.stages}
    assert any(
        stage.replan_reason in {"relative_forecast_error", "absolute_forecast_error", "state_risk"}
        for stage in prepared.stages
    )


def test_tools_only_low_capacity_case_scores_ecology_without_process_failure() -> None:
    adapter = RealEventDataAdapter()
    stage = StaticRealDataWorkflow(adapter).prepare("2022032223").stages[0]

    result = DeterministicToolRunner().run_scenario(stage.payload)

    assert result["process_success"] is True
    assert result["outflow"] == pytest.approx(0.0)
    assert result["safety_status"]["status"] == "safe"
    assert result["evaluation_metrics"]["ecological_score"] < 100.0
    assert result["evaluation_metrics"]["hard_constraint_violations_count"] == 0


def test_rolling_forecast_error_stress_case_uses_real_event_with_derived_predict() -> None:
    adapter = RealEventDataAdapter()

    event = adapter.load_forecast_error_event("2024072617", "under-peak")
    prepared = RollingRealDataWorkflow(adapter).prepare("stress://2024072617?pattern=under-peak")

    assert event.has_prediction is True
    assert event.forecast_error_pattern == "under-peak"
    assert event.records[0].predict == pytest.approx(event.records[0].inflow * 0.8)
    assert prepared.success is True
    assert prepared.diagnostics["forecast_error_pattern"] == "under-peak"


def test_agno_model_builder_fails_first_when_agno_missing(monkeypatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("agno"):
            raise ImportError("blocked agno import for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(RuntimeError, match="Agno is required"):
        build_agno_model(
            {
                "provider": "deepseek",
                "model_id": "deepseek-chat",
                "api_key": "test-key",
                "base_url": "https://api.deepseek.com",
            }
        )
