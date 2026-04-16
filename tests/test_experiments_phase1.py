from __future__ import annotations

import importlib
import json
import sys
import types

import pytest

from pyresops.agents.runner import ReservoirAgentRunner
from experiments.result_schema import StaticResult
from experiments.scenario_config import get_automated_scenarios, get_dynamic_triggers, get_scenario
from experiments.utils.statistical_analysis import (
    compute_phase2_statistics,
    load_results_by_experiment_type,
)


def _import_unified_runner_with_stub(monkeypatch: pytest.MonkeyPatch):
    stub = types.SimpleNamespace(
        aggregate_results=lambda results: {},
        run_all_deviation_experiments=lambda **kwargs: [],
    )
    monkeypatch.setitem(sys.modules, "experiments.automated_experiment", stub)
    sys.modules.pop("experiments.unified_runner", None)
    return importlib.import_module("experiments.unified_runner")


def test_result_schema_rejects_cross_type_fields() -> None:
    with pytest.raises(TypeError):
        StaticResult(
            scenario_id="S01",
            seed=42,
            run_index=0,
            llm_temperature=0.0,
            proposed_outflow=350.0,
            executed_outflow=350.0,
            final_level=156.2,
            peak_outflow=350.0,
            constraint_violations=0,
            dead_level_violations=0,
            normal_level_violations=0,
            ecological_violations=0,
            overall_score=0.9,
            flood_control_score=0.9,
            water_supply_score=0.8,
            power_generation_score=0.7,
            ecological_score=1.0,
            compliance_score=1.0,
            task_completed=True,
            decision_time=0.1,
            tool_call_count=3,
            textual_explanation="ok",
            stage_id="T0",
        )


def test_extract_outflow_prefers_json_and_falls_back_to_regex() -> None:
    parsed_json = ReservoirAgentRunner.extract_outflow(
        '{"outflow": 350.0, "reasoning": "safe", "constraint_check": "passed"}',
        fallback_outflow=100.0,
    )
    assert parsed_json["outflow"] == 350.0
    assert parsed_json["parsed_from"] == "json"
    assert parsed_json["parse_warning"] is None

    parsed_regex = ReservoirAgentRunner.extract_outflow(
        "Recommended outflow: 420 m3/s",
        fallback_outflow=100.0,
    )
    assert parsed_regex["outflow"] == 420.0
    assert parsed_regex["parsed_from"] == "regex"
    assert parsed_regex["parse_warning"]


def test_yaml_config_exposes_externalized_scenarios() -> None:
    s01 = get_scenario("S01")
    automated = get_automated_scenarios()["S02"]
    triggers = get_dynamic_triggers()["S03"]

    assert s01["id"] == "S01"
    assert automated["temperature_override"] == 0.0
    assert triggers[1]["stage"] == "T1"
    assert triggers[1]["pass_condition"]["type"] == "best_effort"


def test_unified_runner_writes_json_and_summary(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runner = _import_unified_runner_with_stub(monkeypatch)

    def fake_static_baseline(
        scenario_id: str,
        scenario_override: dict | None = None,
        save_result: bool = False,
    ):
        return {
            "scenario_id": scenario_id,
            "scenario_name": "stub",
            "outflow": 320.0,
            "scores": {
                "overall": 0.81,
                "flood_control": 0.9,
                "water_supply": 0.7,
                "power": 0.6,
                "ecological": 1.0,
            },
            "constraint_violations": 0,
            "tool_call_count": 2,
            "total_time_seconds": 0.25,
            "success": True,
            "final_decision_text": "json",
            "sim_details": {"sim_final_level": 156.1},
        }

    class FakeHumanScheduler:
        def schedule(self, scenario: dict) -> dict:
            return {
                "outflow": 280.0,
                "decision": "human",
                "safety_score": 0.7,
                "benefit_score": 0.6,
                "overall_score": 0.65,
                "constraint_violations": 0,
                "sim_final_level": 156.2,
            }

    monkeypatch.setattr(runner, "run_static_baseline", fake_static_baseline)
    monkeypatch.setattr(runner, "HumanBaselineScheduler", FakeHumanScheduler)

    results = runner.run_all(
        experiment_types=["static"],
        scenarios=["S01"],
        seeds=[42],
        repeats=1,
        output_dir=str(tmp_path),
    )

    assert len(results) == 2
    payload = json.loads((tmp_path / "static" / "S01_seed_42.json").read_text(encoding="utf-8"))
    assert payload["experiment_type"] == "static"
    assert payload["llm_temperature"] == 0.0

    summary = runner.summarize_results(results)
    assert summary.loc[0, "scenario_id"] == "S01"
    assert summary.loc[0, "experiment_type"] == "static"


def test_unified_runner_rejects_legacy_automated_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    runner = _import_unified_runner_with_stub(monkeypatch)
    with pytest.raises(ValueError, match="Unsupported experiment type: automated"):
        runner.run_all(
            experiment_types=["automated"],
            scenarios=["S02"],
            seeds=[42],
            repeats=1,
            output_dir=str(tmp_path),
        )


def test_unified_runner_deviation_path_in_run_all(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    runner = _import_unified_runner_with_stub(monkeypatch)
    from experiments.result_schema import RollingControlResult

    def fake_run_all_deviation_experiments(
        scenario_ids=None, controller_types=None, model_profile=None
    ):
        return [
            RollingControlResult(
                scenario_id="S02",
                deviation_id="S02-D0",
                deviation_type="none",
                controller_type="llm_tool",
                total_constraint_violations=0,
                max_level_exceedance=0.0,
                has_critical_risk=False,
                key_dimension_scores={"flood_control_score": 0.9},
                overall_score=0.9,
                performance_degradation=0.0,
                correction_count=1,
                effective_correction_count=1,
                effective_correction_rate=1.0,
                recovery_steps=0,
                raw_eval_results=[],
            )
        ]

    monkeypatch.setattr(runner, "run_all_deviation_experiments", fake_run_all_deviation_experiments)

    results = runner.run_all(
        experiment_types=["deviation"],
        scenarios=["S02"],
        seeds=[42],
        repeats=1,
        output_dir=str(tmp_path),
    )

    assert len(results) == 1
    assert isinstance(results[0], RollingControlResult)
    assert results[0].controller_type == "llm_tool"


def test_statistical_analysis_groups_without_none_fields(tmp_path) -> None:
    static_dir = tmp_path / "static"
    dynamic_dir = tmp_path / "dynamic"
    static_dir.mkdir()
    dynamic_dir.mkdir()

    static_dir.joinpath("s01.json").write_text(
        json.dumps(
            {
                "scenario_id": "S01",
                "experiment_type": "static",
                "overall_score": 0.8,
                "constraint_violations": 0,
            }
        ),
        encoding="utf-8",
    )
    dynamic_dir.joinpath("s01_t0.json").write_text(
        json.dumps(
            {
                "scenario_id": "S01",
                "experiment_type": "dynamic",
                "overall_score": 0.7,
                "constraint_violations": 1,
                "stage_id": "T0",
                "partial_credit_score": 0.5,
            }
        ),
        encoding="utf-8",
    )

    grouped = load_results_by_experiment_type(str(tmp_path))

    assert set(grouped) == {"static", "dynamic"}
    assert "stage_id" not in grouped["static"].columns or grouped["static"]["stage_id"].isna().all()


def test_phase2_statistics_static_wilcoxon_and_dynamic_partial_credit(tmp_path) -> None:
    static_dir = tmp_path / "static"
    dynamic_dir = tmp_path / "dynamic"
    automated_dir = tmp_path / "automated"
    static_dir.mkdir()
    dynamic_dir.mkdir()
    automated_dir.mkdir()

    for i, pair in enumerate([(0.7, 0.5), (0.8, 0.6), (0.9, 0.55), (0.85, 0.65), (0.88, 0.62)]):
        llm, human = pair
        static_dir.joinpath(f"S01_seed_{42 + i}.json").write_text(
            json.dumps(
                {
                    "scenario_id": "S01",
                    "experiment_type": "static",
                    "overall_score": llm,
                    "constraint_violations": 0,
                    "llm_temperature": 0.0,
                }
            ),
            encoding="utf-8",
        )
        static_dir.joinpath(f"S01_human_seed_{42 + i}.json").write_text(
            json.dumps(
                {
                    "scenario_id": "S01",
                    "experiment_type": "static_human",
                    "overall_score": human,
                    "constraint_violations": 0,
                    "llm_temperature": 0.0,
                }
            ),
            encoding="utf-8",
        )

    dynamic_dir.joinpath("S03_seed_42_stage_T1.json").write_text(
        json.dumps(
            {
                "scenario_id": "S03",
                "experiment_type": "dynamic",
                "stage_id": "T1",
                "task_completed": False,
                "constraint_violations": 1,
                "partial_credit_score": 0.0,
                "llm_temperature": 0.0,
                "overall_score": 0.4,
            }
        ),
        encoding="utf-8",
    )
    dynamic_dir.joinpath("S03_seed_43_stage_T1.json").write_text(
        json.dumps(
            {
                "scenario_id": "S03",
                "experiment_type": "dynamic",
                "stage_id": "T1",
                "task_completed": True,
                "constraint_violations": 0,
                "partial_credit_score": 1.0,
                "llm_temperature": 0.0,
                "overall_score": 0.8,
            }
        ),
        encoding="utf-8",
    )

    automated_dir.joinpath("S02_seed_42.json").write_text(
        json.dumps(
            {
                "scenario_id": "S02",
                "experiment_type": "automated",
                "key_dimension_gain": 0.2,
                "switch_rate": 0.4,
                "llm_temperature": 0.0,
                "overall_score": 0.9,
                "constraint_violations": 0,
            }
        ),
        encoding="utf-8",
    )

    stats = compute_phase2_statistics(str(tmp_path))

    assert "S01" in stats["static"]
    assert "wilcoxon" in stats["static"]["S01"]
    assert "S03_T1_partial_credit" in stats["dynamic"]
    assert stats["automated"]["S02"]["key_dimension_gain_95_ci"]


def test_deviation_tier_summary_and_grouping(monkeypatch, tmp_path) -> None:
    runner = _import_unified_runner_with_stub(monkeypatch)
    from experiments.result_schema import RollingControlResult

    def fake_run_all_deviation_experiments(
        scenario_ids=None, controller_types=None, model_profile=None
    ):
        return [
            RollingControlResult(
                scenario_id="S02",
                deviation_id="S02-D0",
                deviation_type="none",
                controller_type="static",
                total_constraint_violations=1,
                max_level_exceedance=0.0,
                has_critical_risk=False,
                key_dimension_scores={"flood_control_score": 0.8},
                overall_score=0.8,
                performance_degradation=0.0,
                correction_count=1,
                effective_correction_count=0,
                effective_correction_rate=0.0,
                recovery_steps=0,
                raw_eval_results=[],
            ),
            RollingControlResult(
                scenario_id="S02",
                deviation_id="S02-D0",
                deviation_type="none",
                controller_type="llm_tool",
                total_constraint_violations=0,
                max_level_exceedance=0.0,
                has_critical_risk=False,
                key_dimension_scores={"flood_control_score": 0.9},
                overall_score=0.9,
                performance_degradation=0.0,
                correction_count=1,
                effective_correction_count=1,
                effective_correction_rate=1.0,
                recovery_steps=0,
                raw_eval_results=[],
            ),
        ]

    monkeypatch.setattr(runner, "run_all_deviation_experiments", fake_run_all_deviation_experiments)
    monkeypatch.setattr(
        runner,
        "aggregate_deviation_results",
        lambda results: {
            "static": {"count": 1},
            "llm_tool": {"count": 1},
        },
    )

    summary = runner.run_deviation_tier(output_dir=str(tmp_path))

    assert "static" in summary["summary"]
    assert "llm_tool" in summary["summary"]
    assert (tmp_path / "deviation" / "deviation_results.json").exists()
    assert (tmp_path / "deviation" / "deviation_summary.json").exists()
