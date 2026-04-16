from __future__ import annotations

from experiments.automated_experiment import (
    AUTOMATED_SCENARIOS,
    DeviationScenarioSimulator,
    RuleBasedAdjustmentController,
)


def test_deviation_scenario_simulator_s02_generates_structured_sequence() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    deviation = cfg["deviation_scenarios"][0]
    updates = DeviationScenarioSimulator(cfg, deviation).generate_sequence()

    assert len(updates) > 0
    assert updates[0].deviation_id.startswith("S02-")
    assert updates[0].forecast_inflow >= 0
    assert updates[0].actual_inflow >= 0


def test_deviation_scenario_simulator_s02_is_deterministic_and_uses_reference_profile() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    deviation = cfg["deviation_scenarios"][0]

    updates_1 = DeviationScenarioSimulator(cfg, deviation).generate_sequence()
    updates_2 = DeviationScenarioSimulator(cfg, deviation).generate_sequence()

    assert [(u.elapsed_hours, u.forecast_inflow, u.actual_inflow) for u in updates_1] == [
        (u.elapsed_hours, u.forecast_inflow, u.actual_inflow) for u in updates_2
    ]
    assert len(updates_1) == cfg["reproducibility"]["expected_update_count"]
    assert [u.forecast_inflow for u in updates_1] == [u.actual_inflow for u in updates_1]
    peak_update = max(updates_1, key=lambda item: item.actual_inflow)
    assert peak_update.elapsed_hours == 24.0


def test_deviation_scenario_simulator_s02_timing_shift_changes_peak_hour() -> None:
    cfg = AUTOMATED_SCENARIOS["S02"].copy()
    baseline = cfg["deviation_scenarios"][0]
    early = cfg["deviation_scenarios"][1]

    baseline_updates = DeviationScenarioSimulator(cfg, baseline).generate_sequence()
    early_updates = DeviationScenarioSimulator(cfg, early).generate_sequence()

    baseline_peak = max(baseline_updates, key=lambda item: item.actual_inflow)
    early_peak = max(early_updates, key=lambda item: item.actual_inflow)
    assert baseline_peak.elapsed_hours == 24.0
    assert early_peak.elapsed_hours == 18.0


def test_rule_based_controller_returns_rolling_control_result() -> None:
    cfg = AUTOMATED_SCENARIOS["S04"].copy()
    deviation = cfg["deviation_scenarios"][1]
    updates = DeviationScenarioSimulator(cfg, deviation).generate_sequence()

    result = RuleBasedAdjustmentController(cfg, deviation).run(updates, baseline_score=1.0)

    assert result.controller_type == "rule_based"
    assert result.scenario_id == "S04"
    assert result.deviation_id == deviation["id"]
    assert result.correction_count >= 0
    assert 0.0 <= result.effective_correction_rate <= 1.0


def test_rule_based_controller_uses_configured_schedule_interval() -> None:
    cfg = AUTOMATED_SCENARIOS["S04"].copy()
    cfg["controller_config"] = dict(cfg["controller_config"])
    cfg["controller_config"]["scheduled_update_interval_steps"] = 2
    deviation = cfg["deviation_scenarios"][0]
    updates = DeviationScenarioSimulator(cfg, deviation).generate_sequence()

    result = RuleBasedAdjustmentController(cfg, deviation).run(updates, baseline_score=1.0)

    assert result.forecast_steps == len(updates)
    assert result.correction_count == 2
