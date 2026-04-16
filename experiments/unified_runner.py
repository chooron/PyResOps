from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.automated_experiment import aggregate_results as aggregate_deviation_results
from experiments.automated_experiment import run_all_deviation_experiments
from experiments.baseline_human import HumanBaselineScheduler
from experiments.dynamic_experiment import run_multi_round_dynamic_experiment, run_static_baseline
from experiments.result_schema import (
    DynamicResult,
    ExperimentResult,
    RollingControlResult,
    StaticResult,
)
from experiments.scenario_config import get_scenario


def _scenario_with_temperature(scenario_id: str, llm_temperature: float) -> dict:
    runtime_sc = get_scenario(scenario_id)
    assert runtime_sc["id"] == scenario_id, (
        f"Scenario ID mismatch: YAML key '{scenario_id}' != runtime id '{runtime_sc['id']}'"
    )
    runtime_sc["temperature_override"] = llm_temperature
    return runtime_sc


def _violation_breakdown(
    final_level: float, peak_outflow: float, scenario: dict
) -> tuple[int, int, int]:
    dead = int(final_level < float(scenario.get("dead_level", 120.0)))
    normal = int(final_level > float(scenario.get("flood_limit_level", 156.5)))
    ecological = int(peak_outflow < 50.0)
    return dead, normal, ecological


def _save_result(result: ExperimentResult, output_dir: Path, filename: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(result.to_json(), encoding="utf-8")


def _build_static_result(
    raw: dict, scenario: dict, seed: int, run_index: int, llm_temperature: float
) -> StaticResult:
    final_level = float(
        raw.get("sim_details", {}).get("sim_final_level", scenario["current_level"])
    )
    executed_outflow = float(raw["outflow"])
    dead, normal, ecological = _violation_breakdown(final_level, executed_outflow, scenario)
    return StaticResult(
        scenario_id=scenario["id"],
        seed=seed,
        run_index=run_index,
        llm_temperature=llm_temperature,
        proposed_outflow=executed_outflow,
        executed_outflow=executed_outflow,
        final_level=final_level,
        peak_outflow=executed_outflow,
        constraint_violations=int(raw.get("constraint_violations", 0)),
        dead_level_violations=dead,
        normal_level_violations=normal,
        ecological_violations=ecological,
        overall_score=float(raw["scores"]["overall"]),
        flood_control_score=float(raw["scores"]["flood_control"]),
        water_supply_score=float(raw["scores"]["water_supply"]),
        power_generation_score=float(raw["scores"]["power"]),
        ecological_score=float(raw["scores"]["ecological"]),
        compliance_score=1.0 if int(raw.get("constraint_violations", 0)) == 0 else 0.0,
        task_completed=bool(raw.get("success", False)),
        decision_time=float(raw.get("total_time_seconds", 0.0)),
        tool_call_count=int(raw.get("tool_call_count", 0)),
        textual_explanation=str(raw.get("final_decision_text", "")),
    )


def _build_human_static_result(scenario: dict, seed: int, run_index: int) -> StaticResult:
    scheduler = HumanBaselineScheduler()
    human = scheduler.schedule(scenario)
    final_level = float(human.get("sim_final_level", scenario["current_level"]))
    executed_outflow = float(human.get("outflow", scenario["inflow"]))
    dead, normal, ecological = _violation_breakdown(final_level, executed_outflow, scenario)
    return StaticResult(
        scenario_id=scenario["id"],
        experiment_type="static_human",
        seed=seed,
        run_index=run_index,
        llm_temperature=0.0,
        proposed_outflow=executed_outflow,
        executed_outflow=executed_outflow,
        final_level=final_level,
        peak_outflow=executed_outflow,
        constraint_violations=int(human.get("constraint_violations", 0)),
        dead_level_violations=dead,
        normal_level_violations=normal,
        ecological_violations=ecological,
        overall_score=float(human.get("overall_score", 0.0)),
        flood_control_score=float(human.get("safety_score", 0.0)),
        water_supply_score=float(human.get("benefit_score", 0.0)),
        power_generation_score=float(human.get("benefit_score", 0.0)),
        ecological_score=float(human.get("overall_score", 0.0)),
        compliance_score=1.0 if int(human.get("constraint_violations", 0)) == 0 else 0.0,
        task_completed=True,
        decision_time=0.0,
        tool_call_count=0,
        textual_explanation=str(human.get("decision", "human baseline")),
    )


def _build_dynamic_results(
    raw: dict, scenario: dict, seed: int, run_index: int, llm_temperature: float
) -> list[DynamicResult]:
    results: list[DynamicResult] = []
    previous_outflow = float(scenario["initial_inflow"])
    previous_direction: str | None = None
    for stage in raw.get("stages", []):
        evaluation = stage.get("evaluation", {})
        compliance = stage.get("compliance", {})
        outflow = float(stage.get("llm_outflow", scenario["inflow"]))
        final_level = float(
            stage.get("state_after_sim", {}).get("level", scenario["current_level"])
        )
        direction = (
            "increase"
            if outflow > previous_outflow
            else "decrease"
            if outflow < previous_outflow
            else "maintain"
        )
        dead, normal, ecological = _violation_breakdown(final_level, outflow, scenario)
        results.append(
            DynamicResult(
                scenario_id=scenario["id"],
                seed=seed,
                run_index=run_index,
                llm_temperature=llm_temperature,
                proposed_outflow=outflow,
                executed_outflow=outflow,
                final_level=final_level,
                peak_outflow=outflow,
                constraint_violations=int(evaluation.get("constraint_violations", 0)),
                dead_level_violations=dead,
                normal_level_violations=normal,
                ecological_violations=ecological,
                overall_score=float(evaluation.get("overall_score", 0.0)),
                flood_control_score=float(evaluation.get("flood_control_score", 0.0)),
                water_supply_score=float(evaluation.get("water_supply_score", 0.0)),
                power_generation_score=float(evaluation.get("power_generation_score", 0.0)),
                ecological_score=float(evaluation.get("ecological_score", 0.0)),
                compliance_score=1.0
                if int(evaluation.get("constraint_violations", 0)) == 0
                else 0.0,
                task_completed=bool(compliance.get("pass", False)),
                decision_time=float(stage.get("total_time_seconds", 0.0)),
                tool_call_count=int(stage.get("tool_call_count", 0)),
                textual_explanation=str(stage.get("final_decision_text", "")),
                stage_id=str(stage.get("stage", "")),
                instruction_complied=bool(compliance.get("pass", False)),
                outflow_change_magnitude=round(abs(outflow - previous_outflow), 4),
                strategy_oscillation=(
                    previous_direction is not None
                    and direction != previous_direction
                    and direction != "maintain"
                ),
                partial_credit_score=float(compliance.get("partial_credit", 0.0)),
            )
        )
        previous_outflow = outflow
        if direction != "maintain":
            previous_direction = direction
    return results


def run_all(
    experiment_types: list[str],
    scenarios: list[str],
    seeds: list[int],
    repeats: int = 5,
    output_dir: str = "experiments/results",
) -> list[ExperimentResult | RollingControlResult]:
    results: list[ExperimentResult | RollingControlResult] = []
    root = Path(output_dir)
    normalized_types = [experiment_type.lower() for experiment_type in experiment_types]

    for experiment_type in normalized_types:
        for scenario_id in scenarios:
            for seed in seeds or [0]:
                for run_index in range(repeats):
                    scenario = _scenario_with_temperature(scenario_id, llm_temperature=0.0)

                    if experiment_type == "static":
                        raw = run_static_baseline(
                            scenario_id,
                            scenario_override=scenario,
                            save_result=False,
                        )
                        result = _build_static_result(raw, scenario, seed, run_index, 0.0)
                        suffix = (
                            f"{scenario_id}_seed_{seed}.json"
                            if repeats == 1
                            else f"{scenario_id}_seed_{seed}_run_{run_index}.json"
                        )
                        _save_result(result, root / "static", suffix)
                        results.append(result)

                        human_result = _build_human_static_result(scenario, seed, run_index)
                        human_suffix = (
                            f"{scenario_id}_human_seed_{seed}.json"
                            if repeats == 1
                            else f"{scenario_id}_human_seed_{seed}_run_{run_index}.json"
                        )
                        _save_result(human_result, root / "static", human_suffix)
                        results.append(human_result)
                        continue

                    if experiment_type == "dynamic":
                        raw = run_multi_round_dynamic_experiment(
                            scenario_id,
                            experiment=None,
                            scenario_override=scenario,
                            save_result=False,
                        )
                        dynamic_results = _build_dynamic_results(
                            raw, scenario, seed, run_index, 0.0
                        )
                        for item in dynamic_results:
                            suffix = (
                                f"{scenario_id}_seed_{seed}_stage_{item.stage_id}.json"
                                if repeats == 1
                                else f"{scenario_id}_seed_{seed}_run_{run_index}_stage_{item.stage_id}.json"
                            )
                            _save_result(item, root / "dynamic", suffix)
                        results.extend(dynamic_results)
                        continue

                    if experiment_type == "deviation":
                        first_seed = (seeds or [0])[0]
                        if seed != first_seed or run_index != 0:
                            continue
                        controllers = ["static", "rule_based", "llm_tool"]
                        deviation_results = run_all_deviation_experiments(
                            scenario_ids=[scenario_id],
                            controller_types=controllers,
                        )
                        results.extend(deviation_results)
                        continue

                    raise ValueError(f"Unsupported experiment type: {experiment_type}")

    return results


def run_deviation_tier(
    scenario_ids: list[str] | None = None,
    controller_types: list[str] | None = None,
    model_profile: str | None = None,
    output_dir: str = "experiments/results",
) -> dict:
    scenarios = scenario_ids or ["S02", "S04"]
    controllers = controller_types or ["static", "rule_based", "llm_tool"]
    results = run_all_deviation_experiments(
        scenario_ids=scenarios,
        controller_types=controllers,
        model_profile=model_profile,
    )
    summary = aggregate_deviation_results(results)

    out_dir = Path(output_dir) / "deviation"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = [result.to_dict() for result in results]
    (out_dir / "deviation_results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "deviation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "results": records,
        "summary": summary,
    }


def summarize_results(results: list[ExperimentResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()

    base_results = [result for result in results if hasattr(result, "experiment_type")]
    if not base_results:
        return pd.DataFrame()

    df = pd.DataFrame([result.to_dict() for result in base_results])
    metric_columns = [
        "overall_score",
        "constraint_violations",
        "flood_control_score",
        "water_supply_score",
        "power_generation_score",
        "ecological_score",
        "compliance_score",
        "decision_time",
        "tool_call_count",
        "key_dimension_gain",
        "switch_rate",
        "strategy_oscillation_count",
        "perturbation_seed",
        "partial_credit_score",
    ]
    available_metrics = [column for column in metric_columns if column in df.columns]
    summary = df.groupby(["scenario_id", "experiment_type"])[available_metrics].agg(["mean", "std"])
    summary.columns = [f"{column}_{stat}" for column, stat in summary.columns]
    return summary.reset_index()


def export_tables(df: pd.DataFrame, output_dir: str) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path / "summary_tables.csv", index=False, encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified runner for paper experiments.")
    parser.add_argument("--type", nargs="+", required=True, dest="experiment_types")
    parser.add_argument("--scenarios", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output-dir", default="experiments/results")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    results = run_all(
        experiment_types=args.experiment_types,
        scenarios=args.scenarios,
        seeds=args.seeds,
        repeats=args.repeats,
        output_dir=args.output_dir,
    )
    summary = summarize_results(results)
    if not summary.empty:
        export_tables(summary, args.output_dir)

    deviation_results = [result for result in results if isinstance(result, RollingControlResult)]
    if deviation_results:
        deviation_summary = aggregate_deviation_results(deviation_results)
        deviation_dir = Path(args.output_dir) / "deviation"
        deviation_dir.mkdir(parents=True, exist_ok=True)
        (deviation_dir / "deviation_summary.json").write_text(
            json.dumps(deviation_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
