"""Scenario-style integration tests under the six-family taxonomy."""

from datetime import datetime, timedelta

from pyresops.core import ConstraintValidator, SimulationEngine
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from pyresops.modules import (
    ConstantReleaseModule,
    InflowLinearReleaseModule,
    StorageNonlinearReleaseModule,
)
from pyresops.services import EvaluationService, ExplanationService, ProgramService, SimulationService, SnapshotService


def _forecast(start: datetime, values: list[float]) -> ForecastBundle:
    return ForecastBundle(
        forecast_time=start,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[start + timedelta(hours=index) for index in range(len(values))],
                values=values,
            )
        ],
    )


def test_complete_pipeline_with_constraints(sample_reservoir_spec):
    snapshot_service = SnapshotService()
    program_service = ProgramService()
    simulation_service = SimulationService(sample_reservoir_spec, program_service.get_module_registry())
    evaluation_service = EvaluationService(sample_reservoir_spec)
    explanation_service = ExplanationService()

    state = snapshot_service.create_initial_snapshot("res1", sample_reservoir_spec, 165.0, 8000.0)
    forecast = _forecast(state.timestamp, [8000.0] * 24)
    program = program_service.create_program(
        name="scenario_pipeline",
        time_horizon=TimeHorizon(
            start=state.timestamp,
            end=state.timestamp + timedelta(hours=23),
            time_step=3600,
        ),
        module_configs=[
            {
                "module_type": "storage_nonlinear_release",
                "parameters": {
                    "metric": "storage_ratio",
                    "control_points": [0.0, 0.5, 0.75, 1.0],
                    "release_values": [3000.0, 4500.0, 6000.0, 8000.0],
                },
            }
        ],
    )

    result = simulation_service.run_simulation(program, state, forecast)
    constraint_set = ConstraintSet(
        constraints=[
            Constraint(
                id="level_max",
                name="Maximum level",
                constraint_type="level_max",
                parameters={"max_level": 175.0},
            )
        ]
    )
    violations = ConstraintValidator(constraint_set).validate_simulation(result)
    evaluation = evaluation_service.evaluate(result, constraint_set=constraint_set, include_step_scores=True)
    explanation = explanation_service.explain_program(program, result, evaluation)

    assert result.program_id == program.id
    assert len(result.snapshots) == 24
    assert isinstance(violations, list)
    assert len(evaluation.step_scores) == 24
    assert "summary" in explanation


def test_multi_module_switching_uses_new_family_names(sample_reservoir_spec, sample_initial_state):
    engine = SimulationEngine(sample_reservoir_spec)
    forecast = _forecast(sample_initial_state.timestamp, [8000.0, 9000.0, 22000.0, 12000.0, 7000.0])
    program = DispatchProgram(
        id="three_phase",
        name="three_phase",
        time_horizon=TimeHorizon(
            start=sample_initial_state.timestamp,
            end=sample_initial_state.timestamp + timedelta(hours=4),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_release": 6000.0}),
            ModuleInstance(module_type="storage_nonlinear_release", parameters={
                "metric": "storage_ratio",
                "control_points": [0.0, 0.5, 0.75, 1.0],
                "release_values": [4000.0, 5000.0, 7000.0, 9000.0],
            }),
            ModuleInstance(module_type="inflow_linear_release", parameters={"slope": 1.0}),
        ],
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="storage_nonlinear_release",
                condition_type="inflow_threshold",
                parameters={"threshold": 20000.0, "direction": "above"},
            ),
            SwitchCondition(
                from_module="storage_nonlinear_release",
                to_module="inflow_linear_release",
                condition_type="inflow_threshold",
                parameters={"threshold": 15000.0, "direction": "below"},
            ),
        ],
    )
    modules = {
        "constant_release": ConstantReleaseModule({"target_release": 6000.0}),
        "storage_nonlinear_release": StorageNonlinearReleaseModule(
            {
                "metric": "storage_ratio",
                "control_points": [0.0, 0.5, 0.75, 1.0],
                "release_values": [4000.0, 5000.0, 7000.0, 9000.0],
            }
        ),
        "inflow_linear_release": InflowLinearReleaseModule({"slope": 1.0}),
    }
    result = engine.simulate(program, sample_initial_state, forecast, modules)
    assert len({snapshot.active_module for snapshot in result.snapshots}) >= 2
