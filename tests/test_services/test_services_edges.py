"""Service edge tests under the six-family taxonomy."""

from datetime import datetime

import pytest

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import TimeHorizon
from pyresops.domain.reservoir import DischargeCapacity, LevelStorageCurve, ReservoirSpec
from pyresops.services import (
    EvaluationService,
    ExplanationService,
    OptimizationService,
    ProgramService,
    RollingOpsService,
    SimulationService,
    SnapshotService,
)
from pyresops.storage import Repository


@pytest.fixture
def services():
    spec = ReservoirSpec(
        id="tool_test",
        name="tool_test",
        dead_level=150.0,
        normal_level=175.0,
        flood_limit_level=145.0,
        design_flood_level=180.0,
        check_flood_level=185.0,
        total_capacity=39.3,
        flood_capacity=22.15,
        level_storage_curve=LevelStorageCurve(
            levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
            storages=[0.0, 10.0, 20.0, 30.0, 39.3, 51.6],
        ),
        discharge_capacity=DischargeCapacity(
            levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
            max_discharges=[0.0, 5000.0, 10000.0, 15000.0, 20000.0, 30000.0],
        ),
    )
    snapshot_service = SnapshotService()
    program_service = ProgramService()
    simulation_service = SimulationService(spec, program_service.get_module_registry())
    evaluation_service = EvaluationService(spec)
    explanation_service = ExplanationService()
    optimization_service = OptimizationService(spec, program_service)
    rolling_service = RollingOpsService(
        program_service=program_service,
        simulation_service=simulation_service,
        evaluation_service=evaluation_service,
        optimization_service=optimization_service,
        snapshot_service=snapshot_service,
        repository=Repository(":memory:"),
    )
    return {
        "spec": spec,
        "snapshot": snapshot_service,
        "program": program_service,
        "simulation": simulation_service,
        "evaluation": evaluation_service,
        "explanation": explanation_service,
        "rolling": rolling_service,
    }


def test_list_available_modules_contains_only_new_taxonomy(services):
    modules = services["program"].list_available_modules()
    types = {item["module_type"] for item in modules}
    assert types == {
        "constant_release",
        "inflow_piecewise_constant_release",
        "inflow_linear_release",
        "storage_piecewise_constant_release",
        "storage_nonlinear_release",
        "joint_driven_release",
    }


def test_get_module_registry_contains_only_new_taxonomy(services):
    registry = services["program"].get_module_registry()
    assert set(registry) == {
        "constant_release",
        "inflow_piecewise_constant_release",
        "inflow_linear_release",
        "storage_piecewise_constant_release",
        "storage_nonlinear_release",
        "joint_driven_release",
    }


def test_run_simulation_success(services):
    state = services["snapshot"].create_initial_snapshot("r1", services["spec"], 165.0, 8000.0)
    program = services["program"].create_program(
        "sim_test",
        TimeHorizon(start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 3, 0, 0), time_step=3600),
        [{"module_type": "constant_release", "parameters": {"target_release": 7000.0}}],
    )
    forecast = ForecastBundle(
        forecast_time=datetime(2024, 7, 1),
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[datetime(2024, 7, 1, hour, 0, 0) for hour in range(4)],
                values=[8000.0] * 4,
            )
        ],
    )
    result = services["simulation"].run_simulation(program, state, forecast)
    assert result.program_id == program.id


def test_explain_program_without_simulation(services):
    program = services["program"].create_program(
        "explain_test",
        TimeHorizon(start=datetime(2024, 7, 1), end=datetime(2024, 7, 2), time_step=3600),
        [{"module_type": "constant_release", "parameters": {"target_release": 5000.0}}],
    )
    explanation = services["explanation"].explain_program(program)
    assert "summary" in explanation


def test_rolling_workflow_optimize_reassess_replace_finalize(services):
    state = services["snapshot"].create_initial_snapshot("roll_res", services["spec"], 165.0, 8000.0)
    forecast = ForecastBundle(
        forecast_time=state.timestamp,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[state.timestamp + __import__("datetime").timedelta(hours=hour) for hour in range(12)],
                values=[8000.0 + hour * 200 for hour in range(12)],
            )
        ],
    )

    first = services["rolling"].optimize_release_plan(
        reservoir_id="roll_res",
        context_id="ctx_roll",
        forecast=forecast,
        constraints={"ecological_min_flow": 2000.0},
    )
    reassess = services["rolling"].reassess_plan(
        reservoir_id="roll_res",
        context_id="ctx_roll",
        forecast=forecast,
        constraints={"ecological_min_flow": 2000.0},
    )
    assert reassess["working_plan_id"] == first["candidate_plan_id"]

    second = services["rolling"].optimize_release_plan(
        reservoir_id="roll_res",
        context_id="ctx_roll",
        forecast=forecast,
        constraints={"ecological_min_flow": 2500.0},
    )
    replaced = services["rolling"].replace_working_plan(
        reservoir_id="roll_res",
        context_id="ctx_roll",
        candidate_plan_id=second["candidate_plan_id"],
        reason="operator decision",
    )
    assert replaced["working_plan_id"] == second["candidate_plan_id"]
    finalized = services["rolling"].finalize_plan(reservoir_id="roll_res", context_id="ctx_roll")
    assert "persisted_ids" in finalized
