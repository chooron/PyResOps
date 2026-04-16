from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from experiments.automated_experiment import (
    AUTOMATED_SCENARIOS,
    ForecastUpdate,
    ForecastUpdateSimulator,
    _advance_state,
    _build_runtime_scenario,
    _eval_scenario,
)


RESULTS_DIR = Path(__file__).parent / "results" / "automated"


class HeuristicRollingBaseline:
    """
    非LLM极简滚动基线：
    - 洪水场景：出库 = min(入库, 下游限制)
    - 发电场景：出库 = max(最小生态流量, 来流)
    """

    def _rule_outflow(
        self, scenario_id: str, runtime_scenario: dict, update: ForecastUpdate
    ) -> float:
        inflow = float(update.perturbed_inflow)
        if scenario_id == "S02":
            downstream_limit = float(runtime_scenario.get("downstream_limit", 14000.0))
            return max(50.0, min(inflow, downstream_limit))
        if scenario_id == "S04":
            return max(50.0, inflow)
        return max(50.0, inflow)

    def run(
        self,
        scenario_id: str,
        forecast_updates: list[ForecastUpdate],
        seed: int = 42,
        save_result: bool = True,
    ) -> dict:
        if scenario_id not in AUTOMATED_SCENARIOS:
            raise ValueError(f"场景 {scenario_id} 未定义自动化调度配置")

        cfg = AUTOMATED_SCENARIOS[scenario_id].copy()
        state = {
            "level": float(cfg["current_level"]),
            "storage": float(cfg["initial_storage"]),
            "inflow": float(cfg["initial_inflow"]),
            "outflow": float(cfg["initial_inflow"]),
        }
        interval_hours = int(cfg["forecast_interval_hours"])
        records: list[dict] = []

        for update in forecast_updates:
            runtime_sc = _build_runtime_scenario(cfg, state, update)
            outflow = self._rule_outflow(scenario_id, runtime_sc, update)
            eval_result = _eval_scenario(runtime_sc, outflow)
            advance_hours = min(interval_hours, int(update.remaining_hours))
            state_after = _advance_state(runtime_sc, outflow, advance_hours)

            records.append(
                {
                    "update": asdict(update),
                    "runtime_scenario": {
                        "id": runtime_sc["id"],
                        "inflow": runtime_sc["inflow"],
                        "duration_hours": runtime_sc["duration_hours"],
                    },
                    "heuristic_outflow": round(outflow, 2),
                    "adopted_eval": eval_result,
                    "state_before": state.copy(),
                    "state_after": state_after,
                }
            )
            state = state_after

        final = records[-1] if records else {}
        result = {
            "scenario_id": scenario_id,
            "scenario_name": cfg["name"],
            "seed": seed,
            "perturbation_seed": seed,
            "is_no_switch_baseline": False,
            "is_heuristic_baseline": True,
            "total_forecast_updates": len(forecast_updates),
            "switch_count": 0,
            "switch_rate": 0.0,
            "final_state": state,
            "forecast_updates": [asdict(item) for item in forecast_updates],
            "records": records,
            "final_eval": final.get("adopted_eval", {}),
        }

        if save_result:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            out_path = RESULTS_DIR / f"{scenario_id}_heuristic_seed_{seed}.json"
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        return result


def run_heuristic_baseline(
    scenario_id: str,
    seed: int = 42,
    perturbation_seed: int | None = None,
    save_result: bool = True,
) -> dict:
    cfg = AUTOMATED_SCENARIOS[scenario_id].copy()
    simulator = ForecastUpdateSimulator(
        cfg,
        seed=seed,
        perturbation_seed=perturbation_seed,
    )
    updates = simulator.generate_sequence()
    result = HeuristicRollingBaseline().run(
        scenario_id=scenario_id,
        forecast_updates=updates,
        seed=seed,
        save_result=save_result,
    )
    result["perturbation_seed"] = (
        int(perturbation_seed) if perturbation_seed is not None else int(seed)
    )
    return result


if __name__ == "__main__":
    import sys

    scenario_id = sys.argv[1] if len(sys.argv) > 1 else "S02"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    perturbation_seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
    output = run_heuristic_baseline(
        scenario_id=scenario_id,
        seed=seed,
        perturbation_seed=perturbation_seed,
        save_result=True,
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
