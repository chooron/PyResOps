"""Tests for rolling ops legacy custom rules support."""

from datetime import datetime, timedelta

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


def _build_services(spec):
    snapshot_service = SnapshotService()
    program_service = ProgramService()
    simulation_service = SimulationService(spec, program_service.get_module_registry())
    evaluation_service = EvaluationService(spec)
    optimization_service = OptimizationService(spec, program_service)
    repository = Repository(":memory:")
    return RollingOpsService(
        program_service=program_service,
        simulation_service=simulation_service,
        evaluation_service=evaluation_service,
        optimization_service=optimization_service,
        snapshot_service=snapshot_service,
        repository=repository,
    ), snapshot_service


def _build_forecast(start: datetime) -> ForecastBundle:
    timestamps = [start + timedelta(hours=i) for i in range(12)]
    values = [8000.0 + 100.0 * i for i in range(12)]
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


def test_optimize_accepts_legacy_custom_rules(sample_reservoir_spec) -> None:
    rolling, snapshot_service = _build_services(sample_reservoir_spec)
    state = snapshot_service.create_initial_snapshot("resx", sample_reservoir_spec, 165.0, 8000.0)
    forecast = _build_forecast(state.timestamp)

    result = rolling.optimize_flexible_release_plan(
        reservoir_id="resx",
        context_id="ctxx",
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        forecast=forecast,
        rules=[
            {
                "id": "custom_cap",
                "name": "Custom cap",
                "condition": {"op": "all", "items": []},
                "priority": 1200,
                "actions": [{"action_type": "clamp_outflow", "parameters": {"max": 5000.0}}],
            }
        ],
    )

    assert result["summary"]["decision_trace_steps"] > 0
