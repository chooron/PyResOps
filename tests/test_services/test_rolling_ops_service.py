"""Tests for rolling ops workflow service contracts."""

from datetime import datetime, timedelta

import pytest

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.services import (
    EvaluationService,
    OptimizationService,
    ProgramService,
    RollingOpsService,
    SimulationService,
    SnapshotService,
)
from pyresops.storage import Repository


def _build_forecast(start: datetime, base: float = 8000.0) -> ForecastBundle:
    timestamps = [start + timedelta(hours=i) for i in range(12)]
    values = [base + 100.0 * i for i in range(12)]
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


@pytest.fixture
def rolling_services(sample_reservoir_spec):
    snapshot_service = SnapshotService()
    program_service = ProgramService()
    simulation_service = SimulationService(
        sample_reservoir_spec, program_service.get_module_registry()
    )
    evaluation_service = EvaluationService(sample_reservoir_spec)
    optimization_service = OptimizationService(sample_reservoir_spec, program_service)
    repository = Repository(":memory:")
    rolling = RollingOpsService(
        program_service=program_service,
        simulation_service=simulation_service,
        evaluation_service=evaluation_service,
        optimization_service=optimization_service,
        snapshot_service=snapshot_service,
        repository=repository,
    )
    return {
        "snapshot": snapshot_service,
        "program": program_service,
        "simulation": simulation_service,
        "evaluation": evaluation_service,
        "optimization": optimization_service,
        "repository": repository,
        "rolling": rolling,
    }


def test_reassess_plan_is_read_only(rolling_services, sample_reservoir_spec) -> None:
    ss = rolling_services["snapshot"]
    rolling = rolling_services["rolling"]
    state = ss.create_initial_snapshot("res1", sample_reservoir_spec, 165.0, 8000.0)
    forecast = _build_forecast(state.timestamp)

    optimize_result = rolling.optimize_flexible_release_plan(
        reservoir_id="res1",
        context_id="ctx1",
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        forecast=forecast,
    )
    before = rolling.get_working_state(reservoir_id="res1", context_id="ctx1")

    _ = rolling.reassess_plan(
        reservoir_id="res1",
        context_id="ctx1",
        forecast=_build_forecast(state.timestamp, base=9000.0),
    )
    after = rolling.get_working_state(reservoir_id="res1", context_id="ctx1")

    assert before["working_plan_id"] == after["working_plan_id"]
    assert optimize_result["candidate_plan_id"] == before["working_plan_id"]


def test_replace_working_plan_mutates_only_on_explicit_call(
    rolling_services,
    sample_reservoir_spec,
) -> None:
    ss = rolling_services["snapshot"]
    rolling = rolling_services["rolling"]
    state = ss.create_initial_snapshot("res1", sample_reservoir_spec, 165.0, 8000.0)

    first = rolling.optimize_flexible_release_plan(
        reservoir_id="res1",
        context_id="ctx2",
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        forecast=_build_forecast(state.timestamp, base=7000.0),
    )
    second = rolling.optimize_flexible_release_plan(
        reservoir_id="res1",
        context_id="ctx2",
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        forecast=_build_forecast(state.timestamp, base=10000.0),
    )

    state_before_replace = rolling.get_working_state(reservoir_id="res1", context_id="ctx2")
    assert state_before_replace["working_plan_id"] == first["candidate_plan_id"]

    rolling.replace_working_plan(
        reservoir_id="res1",
        context_id="ctx2",
        candidate_plan_id=second["candidate_plan_id"],
        reason="operator explicit replace",
    )
    state_after_replace = rolling.get_working_state(reservoir_id="res1", context_id="ctx2")
    assert state_after_replace["working_plan_id"] == second["candidate_plan_id"]


def test_finalize_plan_persists_append_only_history(
    rolling_services, sample_reservoir_spec
) -> None:
    ss = rolling_services["snapshot"]
    rolling = rolling_services["rolling"]
    repo = rolling_services["repository"]
    state = ss.create_initial_snapshot("res2", sample_reservoir_spec, 166.0, 7800.0)

    first = rolling.optimize_flexible_release_plan(
        reservoir_id="res2",
        context_id="ctx3",
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        forecast=_build_forecast(state.timestamp, base=7600.0),
    )
    finalize_1 = rolling.finalize_plan(reservoir_id="res2", context_id="ctx3")

    second = rolling.optimize_flexible_release_plan(
        reservoir_id="res2",
        context_id="ctx3",
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        forecast=_build_forecast(state.timestamp, base=9200.0),
    )
    rolling.replace_working_plan(
        reservoir_id="res2",
        context_id="ctx3",
        candidate_plan_id=second["candidate_plan_id"],
        reason="new forecast",
    )
    finalize_2 = rolling.finalize_plan(reservoir_id="res2", context_id="ctx3")

    records = repo.list_finalized_records(reservoir_id="res2", context_id="ctx3")
    assert len(records) == 2
    ids = {record["finalized_id"] for record in records}
    assert finalize_1["persisted_ids"]["finalized_id"] in ids
    assert finalize_2["persisted_ids"]["finalized_id"] in ids

    program_1 = repo.load_program(finalize_1["persisted_ids"]["program_id"])
    program_2 = repo.load_program(finalize_2["persisted_ids"]["program_id"])
    assert program_1 is not None
    assert program_2 is not None
    assert program_1["id"] != program_2["id"]
