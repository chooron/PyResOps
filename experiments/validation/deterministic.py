"""Deterministic tools-only baseline for real-data validation."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Any

from pyresops.agents.runner import ReservoirAgentRunner
from pyresops.agents.specs import load_default_experiment_spec
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import TimeHorizon
from pyresops.domain.reservoir import ReservoirState
from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
from pyresops.services import EvaluationService, OptimizationService, ProgramService, SimulationService


class DeterministicToolRunner:
    """Run the required tool chain directly through PyResOps services."""

    model_id = "tools-only"
    model_profile = "deterministic_tools_only"

    def run_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        started_at = ReservoirAgentRunner._utc_now()
        wall_start = time.time()
        spec = load_default_experiment_spec()
        tool_events: list[dict[str, Any]] = []
        call_order = 1

        status_payload = self._status_payload(payload, spec)
        tool_events.append(self._event(call_order, "get_reservoir_status", status_payload))
        call_order += 1
        rules_payload = self._rules_payload(payload, spec)
        tool_events.append(self._event(call_order, "query_dispatch_rules", rules_payload))
        call_order += 1

        initial_state, planning_forecast = self._build_context(
            payload,
            use_prediction=payload.get("workflow_type") == "rolling",
        )
        _, observed_forecast = self._build_context(payload, use_prediction=False)
        carry_over_plan = payload.get("carry_over_plan")
        if isinstance(carry_over_plan, dict) and carry_over_plan:
            carry_simulation = self._simulate_module(
                payload=payload,
                spec=spec,
                initial_state=initial_state,
                forecast=observed_forecast,
                module_type=str(carry_over_plan.get("module_type", "constant_release")),
                module_parameters=dict(
                    carry_over_plan.get("module_parameters")
                    or {"target_release": float(carry_over_plan["outflow"])}
                ),
            )
            carry_sim_payload = self._simulation_payload(
                payload=payload,
                simulation=carry_simulation,
                module_type=str(carry_over_plan.get("module_type", "constant_release")),
                module_parameters=dict(
                    carry_over_plan.get("module_parameters")
                    or {"target_release": float(carry_over_plan["outflow"])}
                ),
            )
            tool_events.append(
                self._event(call_order, "simulate_dispatch_program", carry_sim_payload)
            )
            call_order += 1
            carry_eval_payload = self._evaluate_payload(
                payload=payload,
                spec=spec,
                simulation=carry_simulation,
                module_type=carry_sim_payload["module_type"],
                module_parameters=carry_sim_payload["module_parameters"],
            )
            tool_events.append(
                self._event(call_order, "evaluate_dispatch_result", carry_eval_payload)
            )
            call_order += 1

        constraints = {
            "max_release": float(spec.discharge_capacity.get_max_discharge(initial_state.level)),
            "max_level": float(spec.check_flood_level),
            "min_level": float(spec.dead_level),
        }
        optimization = OptimizationService(spec, ProgramService()).optimize_release_plan(
            initial_state=initial_state,
            forecast=planning_forecast,
            constraints=constraints,
            task_constraints={
                "target_level": float(payload["target_level"]),
                "target_tolerance": float(payload.get("target_level_tolerance", 0.5)),
            },
            objectives={"target_level": float(payload["target_level"])},
            name=f"{payload['id']}_tools_only",
            metadata={"scenario_id": payload["id"], "workflow_type": payload.get("workflow_type")},
        )
        selected = optimization.selected_candidate
        release_values = [float(snap.outflow) for snap in selected.simulation_result.snapshots]
        optimize_payload = {
            "scenario_id": payload["id"],
            "program_id": optimization.program.id,
            "selected_module_type": selected.module_type,
            "selected_module_parameters": selected.module_parameters,
            "feasible_solution_found": selected.feasible,
            "fallback_applied": optimization.fallback_applied,
            "avg_release_m3s": round(float(selected.simulation_result.avg_outflow), 3),
            "release_values_m3s": [round(value, 3) for value in release_values],
            "family_attempts": optimization.family_attempts,
        }
        tool_events.append(self._event(call_order, "optimize_release_plan", optimize_payload))
        call_order += 1

        simulation = self._simulate_module(
            payload=payload,
            spec=spec,
            initial_state=initial_state,
            forecast=observed_forecast,
            module_type=selected.module_type,
            module_parameters=selected.module_parameters,
        )
        simulate_payload = self._simulation_payload(
            payload=payload,
            simulation=simulation,
            module_type=selected.module_type,
            module_parameters=selected.module_parameters,
        )
        tool_events.append(self._event(call_order, "simulate_dispatch_program", simulate_payload))
        call_order += 1

        evaluation_payload = self._evaluate_payload(
            payload=payload,
            spec=spec,
            simulation=simulation,
            module_type=selected.module_type,
            module_parameters=selected.module_parameters,
        )
        tool_events.append(self._event(call_order, "evaluate_dispatch_result", evaluation_payload))

        final_payload = {
            "status": "success",
            "outflow": round(float(simulation.avg_outflow), 3),
            "module_type": selected.module_type,
            "module_parameters": selected.module_parameters,
            "reasoning": "Deterministic tools-only optimization baseline.",
            "constraint_check": "Evaluated by PyResOps EvaluationService.",
        }
        tool_chain = [event["tool_name"] for event in tool_events]
        failure_reason = ReservoirAgentRunner._validate_profile_chain(
            scenario=payload,
            tool_chain=tool_chain,
            payload=final_payload,
        )
        safety_status = ReservoirAgentRunner._derive_safety_status(evaluation_payload)
        instruction_status = ReservoirAgentRunner._derive_instruction_status(
            scenario=payload,
            evaluation_payload=evaluation_payload,
        )
        success = failure_reason is None
        finished_at = ReservoirAgentRunner._utc_now()
        return {
            "scenario_id": payload["id"],
            "method": "tools_only",
            "model": self.model_id,
            "success": success,
            "outflow": final_payload["outflow"],
            "reasoning": final_payload["reasoning"],
            "constraint_check": final_payload["constraint_check"],
            "process_success": success,
            "protocol_warning": ReservoirAgentRunner._dynamic_protocol_warning(
                scenario=payload,
                tool_chain=tool_chain,
            ),
            "safety_status": safety_status,
            "instruction_status": instruction_status,
            "parse_warning": None,
            "parsed_from": "dict",
            "final_decision_text": json.dumps(final_payload, ensure_ascii=False),
            "tool_call_count": len(tool_chain),
            "tool_call_chain": tool_chain,
            "tool_calls_detail": [
                {"call_order": event["call_order"], "tool_name": event["tool_name"]}
                for event in tool_events
            ],
            "llm_execution_trace": {
                "started_at": started_at,
                "finished_at": finished_at,
                "tool_events": tool_events,
                "attempts": 1,
            },
            "accepted_attempt_index": 1 if success else None,
            "acceptance_failure_reason": failure_reason,
            "accepted_evidence_pair": {"final_payload": final_payload} if success else None,
            "total_time_seconds": round(time.time() - wall_start, 3),
            "llm_temperature": 0.0,
            "llm_seed": None,
            "llm_usage": None,
            "llm_usage_log_path": None,
            "evaluation_metrics": evaluation_payload,
        }

    @staticmethod
    def _event(call_order: int, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "call_order": call_order,
            "tool_name": tool_name,
            "result": json.dumps(payload, ensure_ascii=False, default=str),
        }

    @staticmethod
    def _build_context(
        payload: dict[str, Any],
        *,
        use_prediction: bool,
    ) -> tuple[ReservoirState, ForecastBundle]:
        values_key = (
            "benchmark_predicted_inflow_series_m3s"
            if use_prediction and payload.get("benchmark_predicted_inflow_series_m3s")
            else "benchmark_inflow_series_m3s"
        )
        inflows = [float(value) for value in payload[values_key]]
        start = payload["start_time"]
        step_hours = int(payload["time_step_hours"])
        timestamps = [start + timedelta(hours=step_hours * index) for index in range(len(inflows))]
        state = ReservoirState(
            timestamp=start,
            level=float(payload["current_level"]),
            storage=float(payload["initial_storage"]),
            inflow=float(payload["initial_inflow"]),
            outflow=float(payload.get("initial_outflow", payload["initial_inflow"])),
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
            metadata={"source": values_key},
        )
        return state, forecast

    @staticmethod
    def _status_payload(payload: dict[str, Any], spec) -> dict[str, Any]:
        inflows = [float(value) for value in payload["benchmark_inflow_series_m3s"]]
        predicted = [float(value) for value in payload.get("benchmark_predicted_inflow_series_m3s", [])]
        planning = predicted if payload.get("workflow_type") == "rolling" and predicted else inflows
        return {
            "scenario_id": payload["id"],
            "current_level_m": float(payload["current_level"]),
            "initial_storage_1e8m3": float(payload["initial_storage"]),
            "current_inflow_m3s": float(payload["initial_inflow"]),
            "forecast_mean_inflow_m3s": round(sum(planning) / len(planning), 3),
            "forecast_peak_inflow_m3s": max(planning),
            "observed_mean_inflow_m3s": round(sum(inflows) / len(inflows), 3),
            "observed_peak_inflow_m3s": max(inflows),
            "forecast_source": "predict" if planning is predicted else "observed_inflow",
            "flood_limit_level_m": float(payload["flood_limit_level"]),
            "normal_level_m": float(spec.normal_level),
            "dead_level_m": float(spec.dead_level),
            "workflow_type": payload.get("workflow_type"),
            "stage_offset_hours": payload.get("stage_offset_hours"),
            "operator_instruction": payload.get("operator_instruction"),
            "carry_over_plan": payload.get("carry_over_plan"),
        }

    @staticmethod
    def _rules_payload(payload: dict[str, Any], spec) -> dict[str, Any]:
        max_release = spec.discharge_capacity.get_max_discharge(float(payload["current_level"]))
        return {
            "scenario_id": payload["id"],
            "hard_constraints": {
                "flood_limit_level_m": float(payload["flood_limit_level"]),
                "dead_level_m": float(spec.dead_level),
                "normal_level_m": float(spec.normal_level),
                "max_release_m3s": round(float(max_release), 3),
            },
            "soft_objectives": {
                "ecological_min_flow_m3s": float(payload.get("ecological_min_flow", 50.0)),
                "ecological_min_flow_enforced": False,
            },
            "objectives": {"target_level_m": float(payload["target_level"])},
            "workflow_profile": payload.get("agent_workflow_profile"),
        }

    @staticmethod
    def _simulate_module(
        *,
        payload: dict[str, Any],
        spec,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        module_type: str,
        module_parameters: dict[str, Any],
    ):
        program = ProgramService().create_program(
            name=f"{payload['id']}_tools_only_sim",
            time_horizon=DeterministicToolRunner._build_horizon(forecast),
            module_configs=[{"module_type": module_type, "parameters": module_parameters}],
        )
        return SimulationService(spec, BASE_RELEASE_MODULE_REGISTRY).run_simulation(
            program,
            initial_state.copy_with_update(),
            forecast,
        )

    @staticmethod
    def _build_horizon(forecast: ForecastBundle) -> TimeHorizon:
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
            start=series.timestamps[0],
            end=series.timestamps[-1] + timedelta(seconds=step_seconds),
            time_step=step_seconds,
        )

    @staticmethod
    def _simulation_payload(
        *,
        payload: dict[str, Any],
        simulation,
        module_type: str,
        module_parameters: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "scenario_id": payload["id"],
            "declared_outflow": float(simulation.avg_outflow),
            "module_type": module_type,
            "module_parameters": module_parameters,
            "max_level_m": round(float(simulation.max_level), 3),
            "min_level_m": round(float(simulation.min_level), 3),
            "final_level_m": round(float(simulation.snapshots[-1].level), 3),
            "avg_outflow_m3s": round(float(simulation.avg_outflow), 3),
            "total_steps": len(simulation.snapshots),
        }

    @staticmethod
    def _evaluate_payload(
        *,
        payload: dict[str, Any],
        spec,
        simulation,
        module_type: str,
        module_parameters: dict[str, Any],
    ) -> dict[str, Any]:
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
        evaluation = EvaluationService(spec).evaluate(
            simulation,
            constraint_set=constraint_set,
            proxy_options={"env_min_flow": float(payload.get("ecological_min_flow", 50.0))},
        )
        final_level = float(simulation.snapshots[-1].level)
        target_level = float(payload["target_level"])
        instruction_violations = []
        if final_level > target_level + float(payload.get("target_level_tolerance", 0.5)):
            instruction_violations.append(
                {
                    "constraint_id": "target_level",
                    "message": f"final level {final_level:.3f} exceeds target {target_level:.3f}",
                }
            )
        hard_violations = list(evaluation.constraint_violations)
        return {
            "scenario_id": payload["id"],
            "declared_outflow": float(simulation.avg_outflow),
            "module_type": module_type,
            "module_parameters": module_parameters,
            "final_level_m": round(final_level, 3),
            "target_level_m": target_level,
            "overall_score": round(float(evaluation.overall_score), 4),
            "flood_control_score": round(float(evaluation.flood_control_score), 4),
            "water_supply_score": round(float(evaluation.water_supply_score), 4),
            "power_generation_score": round(float(evaluation.power_generation_score), 4),
            "ecological_score": round(float(evaluation.ecological_score), 4),
            "constraint_violations_count": len(hard_violations),
            "constraint_violations": hard_violations,
            "hard_constraint_violations_count": len(hard_violations),
            "hard_constraint_violations": hard_violations,
            "instruction_violations_count": len(instruction_violations),
            "instruction_violations": instruction_violations,
        }
