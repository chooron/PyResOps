from __future__ import annotations

import pytest

from experiments.automated_experiment import (
    AUTOMATED_SCENARIOS,
    DeviationScenarioSimulator,
    DeviationUpdate,
    LLMToolBasedController,
    run_deviation_experiment,
)
from experiments.scenario_config import CONFIG_PATH, get_automated_scenarios


class StubExperiment:
    def __init__(self, outflow: float):
        self.outflow = outflow

    def run_scenario(self, scenario: dict) -> dict:
        return {
            "scenario_id": scenario["id"],
            "outflow": self.outflow,
            "tool_call_count": 1,
            "total_time_seconds": 0.01,
            "final_decision_text": '{"outflow": 100.0, "reasoning": "x", "constraint_check": "ok"}',
            "success": True,
        }


def _single_update(deviation_id: str) -> list[DeviationUpdate]:
    return [
        DeviationUpdate(
            update_index=0,
            elapsed_hours=0.0,
            remaining_hours=48.0,
            forecast_inflow=3380.0,
            actual_inflow=3380.0,
            deviation_id=deviation_id,
        )
    ]


def test_deviation_simulator_rejects_mismatched_s04_sequence_lengths() -> None:
    cfg = AUTOMATED_SCENARIOS["S04"].copy()
    bad_deviation = {
        "id": "S04-BAD",
        "deviation_type": "bad",
        "xun_actual": [49.0, 52.5, 70.0],
        "xun_forecast": [70.0, 70.0],
    }

    with pytest.raises(ValueError, match="length"):
        DeviationScenarioSimulator(cfg, bad_deviation).generate_sequence()


def test_scenario_config_uses_config_subdir_yaml() -> None:
    assert CONFIG_PATH.as_posix().endswith("experiments/config/scenarios_config.yaml")
    assert CONFIG_PATH.exists()
    assert "S02" in get_automated_scenarios()


def test_run_deviation_experiment_requires_explicit_d0_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import experiments.automated_experiment as automated

    scenario_cfg = AUTOMATED_SCENARIOS["S02"].copy()
    scenario_cfg["deviation_scenarios"] = [
        {
            "id": "S02-DX",
            "deviation_type": "timing_early",
            "actual_peak_flow": 3380.0,
            "actual_peak_hour": 18,
            "forecast_peak_flow": 3380.0,
            "forecast_peak_hour": 24,
        }
    ]

    monkeypatch.setitem(automated.AUTOMATED_SCENARIOS, "S02", scenario_cfg)

    with pytest.raises(ValueError, match="D0"):
        run_deviation_experiment(
            scenario_id="S02",
            deviation_id="S02-DX",
            controller_type="rule_based",
            save_result=False,
        )


def test_static_path_is_pure_code_even_if_experiment_is_provided() -> None:
    class ExplodingExperiment:
        def run_scenario(self, scenario: dict) -> dict:
            raise AssertionError("static baseline must not invoke LLM experiment")

    result = run_deviation_experiment(
        scenario_id="S02",
        deviation_id="S02-D0",
        controller_type="static",
        experiment=ExplodingExperiment(),
        save_result=False,
    )

    assert result.controller_type == "static"
    assert result.forecast_steps > 0


def test_rule_based_path_runs_without_experiment() -> None:
    result = run_deviation_experiment(
        scenario_id="S02",
        deviation_id="S02-D0",
        controller_type="rule_based",
        save_result=False,
    )
    assert result.controller_type == "rule_based"
    assert result.forecast_steps > 0


def test_llm_tool_controller_reports_no_switch_when_threshold_not_met() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    cfg["switch_threshold"] = 999.0
    deviation_cfg = cfg["deviation_scenarios"][0]
    controller = LLMToolBasedController(cfg, StubExperiment(outflow=100.0), switch_threshold=999.0)
    updates = _single_update(deviation_cfg["id"])

    result = controller.run(updates, deviation_cfg, baseline_score=1.0)

    assert result.switch_occurred is False


def test_llm_tool_controller_propagates_runtime_error() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    deviation_cfg = cfg["deviation_scenarios"][0]

    class AlwaysFailExperiment:
        def run_scenario(self, scenario: dict) -> dict:
            raise RuntimeError("missing api key")

    controller = LLMToolBasedController(cfg, AlwaysFailExperiment(), switch_threshold=0.10)
    updates = _single_update(deviation_cfg["id"])

    with pytest.raises(RuntimeError, match="missing api key"):
        controller.run(updates, deviation_cfg, baseline_score=1.0)


def test_llm_tool_controller_requires_real_tool_call_evidence() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    deviation_cfg = cfg["deviation_scenarios"][0]

    class NoToolCallExperiment:
        def run_scenario(self, scenario: dict) -> dict:
            return {"outflow": 120.0, "tool_call_count": 0, "success": True}

    controller = LLMToolBasedController(cfg, NoToolCallExperiment(), switch_threshold=0.10)
    updates = _single_update(deviation_cfg["id"])

    with pytest.raises(RuntimeError, match="real tool call"):
        controller.run(updates, deviation_cfg, baseline_score=1.0)


def test_llm_tool_controller_rejects_non_json_decision_payload() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    deviation_cfg = cfg["deviation_scenarios"][0]

    class BadDecisionPayloadExperiment:
        def run_scenario(self, scenario: dict) -> dict:
            return {
                "outflow": None,
                "tool_call_count": 1,
                "final_decision_text": "not-json",
                "success": True,
            }

    controller = LLMToolBasedController(cfg, BadDecisionPayloadExperiment(), switch_threshold=0.10)
    updates = _single_update(deviation_cfg["id"])

    with pytest.raises(RuntimeError, match="valid JSON"):
        controller.run(updates, deviation_cfg, baseline_score=1.0)
