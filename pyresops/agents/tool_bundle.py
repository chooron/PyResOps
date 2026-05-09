"""Agno tools for real-data reservoir dispatch workflows."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from pyresops.modules import ALLOWED_BASE_RELEASE_MODULE_TYPES


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


class ReservoirToolBundleFactory:
    """Create Agno tools bound to one runtime scenario payload."""

    def __init__(self, scenario_resolver=None):
        self._scenario_resolver = scenario_resolver

    def resolve_scenario_config(
        self,
        scenario_id: str,
        runtime_scenario: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if runtime_scenario and runtime_scenario.get("id") == scenario_id:
            return runtime_scenario
        if self._scenario_resolver is None:
            return None
        return self._scenario_resolver(scenario_id)

    def make_tools(self, spec, runtime_scenario: dict[str, Any] | None = None):
        try:
            from agno.tools import tool as agno_tool
        except ImportError as exc:
            raise RuntimeError(
                "Agno is required to create real workflow tools but is not installed."
            ) from exc

        def get_scenario(scenario_id: str) -> dict[str, Any]:
            scenario = self.resolve_scenario_config(scenario_id, runtime_scenario)
            if scenario is None:
                raise ValueError(f"Unknown scenario_id: {scenario_id}")
            return scenario

        def build_context(sc: dict[str, Any], *, use_prediction: bool = False):
            from pyresops.domain.forecast import ForecastBundle, ForecastSeries
            from pyresops.domain.reservoir import ReservoirState

            step_hours = int(sc["time_step_hours"])
            values_key = (
                "benchmark_predicted_inflow_series_m3s"
                if use_prediction and sc.get("benchmark_predicted_inflow_series_m3s")
                else "benchmark_inflow_series_m3s"
            )
            inflows = [float(value) for value in sc[values_key]]
            if not inflows:
                raise ValueError("Scenario inflow series is empty")
            start = sc["start_time"]
            timestamps = [start + timedelta(hours=step_hours * i) for i in range(len(inflows))]
            state = ReservoirState(
                timestamp=start,
                level=float(sc["current_level"]),
                storage=float(sc["initial_storage"]),
                inflow=float(sc["initial_inflow"]),
                outflow=float(sc.get("initial_outflow", sc["initial_inflow"])),
            )
            forecast = ForecastBundle(
                forecast_time=start,
                series=[
                    ForecastSeries(
                        variable="inflow",
                        timestamps=timestamps,
                        values=inflows,
                        unit="m3/s",
                    )
                ],
            )
            return state, forecast

        def normalize_module_parameters(
            module_type: str,
            target_outflow: float,
            raw_json: str | None,
        ) -> dict[str, Any]:
            if raw_json:
                decoded = json.loads(raw_json)
                if not isinstance(decoded, dict):
                    raise ValueError("module_parameters_json must decode to an object")
                return decoded
            if module_type == "constant_release":
                return {"target_release": float(target_outflow)}
            return {"target_release": float(target_outflow)}

        @agno_tool
        def get_reservoir_status(scenario_id: str) -> str:
            sc = get_scenario(scenario_id)
            inflows = [float(value) for value in sc["benchmark_inflow_series_m3s"]]
            predicted_inflows = [
                float(value) for value in sc.get("benchmark_predicted_inflow_series_m3s", [])
            ]
            planning_inflows = predicted_inflows if sc.get("workflow_type") == "rolling" and predicted_inflows else inflows
            return _json(
                {
                    "scenario_id": scenario_id,
                    "current_level_m": float(sc["current_level"]),
                    "initial_storage_1e8m3": float(sc["initial_storage"]),
                    "current_inflow_m3s": float(sc["initial_inflow"]),
                    "forecast_mean_inflow_m3s": round(sum(planning_inflows) / len(planning_inflows), 3),
                    "forecast_peak_inflow_m3s": max(planning_inflows),
                    "observed_mean_inflow_m3s": round(sum(inflows) / len(inflows), 3),
                    "observed_peak_inflow_m3s": max(inflows),
                    "forecast_source": "predict" if planning_inflows is predicted_inflows else "observed_inflow",
                    "flood_limit_level_m": float(sc["flood_limit_level"]),
                    "normal_level_m": float(spec.normal_level),
                    "dead_level_m": float(spec.dead_level),
                    "data_source": sc.get("data_source"),
                    "workflow_type": sc.get("workflow_type"),
                    "stage_offset_hours": sc.get("stage_offset_hours"),
                    "operator_instruction": sc.get("operator_instruction"),
                    "carry_over_plan": sc.get("carry_over_plan"),
                }
            )

        @agno_tool
        def query_dispatch_rules(scenario_id: str) -> str:
            sc = get_scenario(scenario_id)
            max_release = spec.discharge_capacity.get_max_discharge(float(sc["current_level"]))
            return _json(
                {
                    "scenario_id": scenario_id,
                    "hard_constraints": {
                        "flood_limit_level_m": float(sc["flood_limit_level"]),
                        "dead_level_m": float(spec.dead_level),
                        "normal_level_m": float(spec.normal_level),
                        "max_release_m3s": round(float(max_release), 3),
                    },
                    "soft_objectives": {
                        "ecological_min_flow_m3s": float(sc.get("ecological_min_flow", 50.0)),
                        "ecological_min_flow_enforced": False,
                    },
                    "objectives": {
                        "target_level_m": float(sc["target_level"]),
                        "prefer_verified_tool_candidate": True,
                    },
                    "allowed_module_types": sorted(ALLOWED_BASE_RELEASE_MODULE_TYPES),
                    "workflow_profile": sc.get("agent_workflow_profile"),
                }
            )

        @agno_tool
        def optimize_release_plan(
            scenario_id: str,
            requested_module_type: str = "",
            min_flow: float = 50.0,
            max_flow: float = 0.0,
        ) -> str:
            from pyresops.services import OptimizationService, ProgramService

            sc = get_scenario(scenario_id)
            state, forecast = build_context(
                sc,
                use_prediction=sc.get("workflow_type") == "rolling",
            )
            requested = requested_module_type.strip() or None
            constraints = {
                "max_release": (
                    float(max_flow)
                    if float(max_flow) > 0
                    else float(spec.discharge_capacity.get_max_discharge(state.level))
                ),
                "max_level": float(spec.check_flood_level),
                "min_level": float(spec.dead_level),
            }
            result = OptimizationService(spec, ProgramService()).optimize_release_plan(
                initial_state=state,
                forecast=forecast,
                constraints=constraints,
                task_constraints={
                    "target_level": float(sc["target_level"]),
                    "target_tolerance": float(sc.get("target_level_tolerance", 0.5)),
                },
                objectives={"target_level": float(sc["target_level"])},
                requested_module_type=requested,
                name=f"{scenario_id}_realdata_agent",
                metadata={"scenario_id": scenario_id, "workflow_type": sc.get("workflow_type")},
            )
            selected = result.selected_candidate
            release_values = [
                float(snapshot.outflow) for snapshot in selected.simulation_result.snapshots
            ]
            return _json(
                {
                    "scenario_id": scenario_id,
                    "program_id": result.program.id,
                    "selected_module_type": selected.module_type,
                    "selected_module_parameters": selected.module_parameters,
                    "feasible_solution_found": selected.feasible,
                    "fallback_applied": result.fallback_applied,
                    "avg_release_m3s": round(float(selected.simulation_result.avg_outflow), 3),
                    "release_values_m3s": [round(value, 3) for value in release_values],
                    "family_attempts": result.family_attempts,
                }
            )

        @agno_tool
        def simulate_dispatch_program(
            scenario_id: str,
            target_outflow: float,
            module_type: str = "constant_release",
            module_parameters_json: str = "",
        ) -> str:
            from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
            from pyresops.services import ProgramService, SimulationService

            sc = get_scenario(scenario_id)
            if module_type not in ALLOWED_BASE_RELEASE_MODULE_TYPES:
                raise ValueError(f"Unsupported module_type: {module_type}")
            state, forecast = build_context(sc)
            module_parameters = normalize_module_parameters(
                module_type,
                float(target_outflow),
                module_parameters_json,
            )
            horizon = OptimizationServiceShim.build_horizon(state, forecast)
            program = ProgramService().create_program(
                name=f"{scenario_id}_agent_sim",
                time_horizon=horizon,
                module_configs=[
                    {
                        "module_type": module_type,
                        "parameters": module_parameters,
                    }
                ],
            )
            result = SimulationService(spec, BASE_RELEASE_MODULE_REGISTRY).run_simulation(
                program,
                state,
                forecast,
            )
            return _json(
                {
                    "scenario_id": scenario_id,
                    "declared_outflow": float(target_outflow),
                    "module_type": module_type,
                    "module_parameters": module_parameters,
                    "max_level_m": round(float(result.max_level), 3),
                    "min_level_m": round(float(result.min_level), 3),
                    "final_level_m": round(float(result.snapshots[-1].level), 3),
                    "avg_outflow_m3s": round(float(result.avg_outflow), 3),
                    "total_steps": len(result.snapshots),
                }
            )

        @agno_tool
        def evaluate_dispatch_result(
            scenario_id: str,
            target_outflow: float,
            eco_min_flow: float = 50.0,
            module_type: str = "constant_release",
            module_parameters_json: str = "",
        ) -> str:
            from pyresops.domain.constraint import Constraint, ConstraintSet
            from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
            from pyresops.services import EvaluationService, ProgramService, SimulationService

            sc = get_scenario(scenario_id)
            if module_type not in ALLOWED_BASE_RELEASE_MODULE_TYPES:
                raise ValueError(f"Unsupported module_type: {module_type}")
            state, forecast = build_context(sc)
            module_parameters = normalize_module_parameters(
                module_type,
                float(target_outflow),
                module_parameters_json,
            )
            horizon = OptimizationServiceShim.build_horizon(state, forecast)
            program = ProgramService().create_program(
                name=f"{scenario_id}_agent_eval",
                time_horizon=horizon,
                module_configs=[
                    {
                        "module_type": module_type,
                        "parameters": module_parameters,
                    }
                ],
            )
            sim_result = SimulationService(spec, BASE_RELEASE_MODULE_REGISTRY).run_simulation(
                program,
                state,
                forecast,
            )
            constraint_set = ConstraintSet(
                constraints=[
                    Constraint(
                        id="level_min",
                        name="Minimum level",
                        constraint_type="level_min",
                        parameters={"min_level": float(spec.dead_level)},
                        priority=10,
                    ),
                    Constraint(
                        id="level_max",
                        name="Maximum level",
                        constraint_type="level_max",
                        parameters={"max_level": float(spec.check_flood_level)},
                        priority=10,
                    ),
                ]
            )
            eval_result = EvaluationService(spec).evaluate(
                sim_result,
                constraint_set=constraint_set,
                proxy_options={"env_min_flow": float(eco_min_flow)},
            )
            final_level = float(sim_result.snapshots[-1].level)
            target_level = float(sc["target_level"])
            hard_violations = list(eval_result.constraint_violations)
            instruction_violations = []
            if final_level > target_level + float(sc.get("target_level_tolerance", 0.5)):
                instruction_violations.append(
                    {
                        "constraint_id": "target_level",
                        "message": f"final level {final_level:.3f} exceeds target {target_level:.3f}",
                    }
                )
            return _json(
                {
                    "scenario_id": scenario_id,
                    "declared_outflow": float(target_outflow),
                    "module_type": module_type,
                    "module_parameters": module_parameters,
                    "final_level_m": round(final_level, 3),
                    "target_level_m": target_level,
                    "overall_score": round(float(eval_result.overall_score), 4),
                    "flood_control_score": round(float(eval_result.flood_control_score), 4),
                    "water_supply_score": round(float(eval_result.water_supply_score), 4),
                    "power_generation_score": round(float(eval_result.power_generation_score), 4),
                    "ecological_score": round(float(eval_result.ecological_score), 4),
                    "constraint_violations_count": len(hard_violations),
                    "constraint_violations": hard_violations,
                    "hard_constraint_violations_count": len(hard_violations),
                    "hard_constraint_violations": hard_violations,
                    "instruction_violations_count": len(instruction_violations),
                    "instruction_violations": instruction_violations,
                }
            )

        return [
            get_reservoir_status,
            query_dispatch_rules,
            optimize_release_plan,
            simulate_dispatch_program,
            evaluate_dispatch_result,
        ]


class OptimizationServiceShim:
    """Small local horizon helper shared by simulation/evaluation tools."""

    @staticmethod
    def build_horizon(state, forecast):
        from datetime import timedelta

        from pyresops.domain.program import TimeHorizon

        series = forecast.get_series("inflow")
        if series is None or not series.timestamps:
            raise ValueError("Forecast must include inflow timestamps")
        if len(series.timestamps) >= 2:
            step_seconds = int((series.timestamps[1] - series.timestamps[0]).total_seconds())
        else:
            step_seconds = 3600
        if step_seconds <= 0:
            raise ValueError("Forecast timestamps must be strictly increasing")
        return TimeHorizon(
            start=state.timestamp,
            end=series.timestamps[-1] + timedelta(seconds=step_seconds),
            time_step=step_seconds,
        )
