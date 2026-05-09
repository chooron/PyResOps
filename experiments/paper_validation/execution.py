"""Execution helpers shared by paper-validation runners and tool surfaces."""

from __future__ import annotations

import json
from typing import Any

from experiments.validation.deterministic import DeterministicToolRunner
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.reservoir import ReservoirSpec
from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
from pyresops.services import EvaluationService, OptimizationService, ProgramService, SimulationService


def prepare_event_payload(payload: dict[str, Any], spec: ReservoirSpec) -> dict[str, Any]:
    return {
        "scenario_id": payload["id"],
        "status": DeterministicToolRunner._status_payload(payload, spec),
        "rules": DeterministicToolRunner._rules_payload(payload, spec),
    }


def optimize_release_plan_payload(
    payload: dict[str, Any],
    spec: ReservoirSpec,
    *,
    requested_module_type: str | None = None,
    use_prediction: bool,
) -> dict[str, Any]:
    initial_state, planning_forecast = DeterministicToolRunner._build_context(
        payload,
        use_prediction=use_prediction,
    )
    constraints = {
        "max_release": float(spec.discharge_capacity.get_max_discharge(initial_state.level)),
        "max_level": float(spec.check_flood_level),
        "min_level": float(spec.dead_level),
    }
    result = OptimizationService(spec, ProgramService()).optimize_release_plan(
        initial_state=initial_state,
        forecast=planning_forecast,
        constraints=constraints,
        task_constraints={
            "target_level": float(payload["target_level"]),
            "target_tolerance": float(payload.get("target_level_tolerance", 0.5)),
        },
        objectives={"target_level": float(payload["target_level"])},
        requested_module_type=requested_module_type or None,
        name=f"{payload['id']}_paper_validation",
        metadata={"scenario_id": payload["id"], "workflow_type": payload.get("workflow_type")},
    )
    selected = result.selected_candidate
    release_values = [float(snap.outflow) for snap in selected.simulation_result.snapshots]
    return {
        "scenario_id": payload["id"],
        "program_id": result.program.id,
        "selected_module_type": selected.module_type,
        "selected_module_parameters": selected.module_parameters,
        "feasible_solution_found": selected.feasible,
        "fallback_applied": result.fallback_applied,
        "avg_release_m3s": round(float(selected.simulation_result.avg_outflow), 3),
        "release_values_m3s": [round(value, 3) for value in release_values],
        "family_attempts": result.family_attempts,
    }


def simulate_release_plan_payload(
    payload: dict[str, Any],
    spec: ReservoirSpec,
    *,
    target_outflow: float,
    module_type: str,
    module_parameters: dict[str, Any],
) -> dict[str, Any]:
    initial_state, observed_forecast = DeterministicToolRunner._build_context(
        payload,
        use_prediction=False,
    )
    program = ProgramService().create_program(
        name=f"{payload['id']}_paper_validation_sim",
        time_horizon=DeterministicToolRunner._build_horizon(observed_forecast),
        module_configs=[{"module_type": module_type, "parameters": module_parameters}],
    )
    result = SimulationService(spec, BASE_RELEASE_MODULE_REGISTRY).run_simulation(
        program,
        initial_state.copy_with_update(),
        observed_forecast,
    )
    return {
        "scenario_id": payload["id"],
        "declared_outflow": float(target_outflow),
        "module_type": module_type,
        "module_parameters": module_parameters,
        "simulation_result": result,
        "summary": DeterministicToolRunner._simulation_payload(
            payload=payload,
            simulation=result,
            module_type=module_type,
            module_parameters=module_parameters,
        ),
    }


def evaluate_release_plan_payload(
    payload: dict[str, Any],
    spec: ReservoirSpec,
    *,
    target_outflow: float,
    module_type: str,
    module_parameters: dict[str, Any],
    simulation_result,
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
        simulation_result,
        constraint_set=constraint_set,
        proxy_options={"env_min_flow": float(payload.get("ecological_min_flow", 50.0))},
    )
    summary = DeterministicToolRunner._evaluate_payload(
        payload=payload,
        spec=spec,
        simulation=simulation_result,
        module_type=module_type,
        module_parameters=module_parameters,
    )
    return {
        "scenario_id": payload["id"],
        "declared_outflow": float(target_outflow),
        "module_type": module_type,
        "module_parameters": module_parameters,
        "evaluation_result": evaluation,
        "summary": summary,
    }


def parse_module_parameters(module_type: str, target_outflow: float, raw_json: str | None) -> dict[str, Any]:
    if raw_json:
        decoded = json.loads(raw_json)
        if not isinstance(decoded, dict):
            raise ValueError("module_parameters_json must decode to an object")
        if module_type == "constant_release" and "target_release" not in decoded and "target_flow" not in decoded:
            decoded["target_release"] = float(target_outflow)
        return decoded
    if module_type == "constant_release":
        return {"target_release": float(target_outflow)}
    return {"target_release": float(target_outflow)}
