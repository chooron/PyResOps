"""Tests for optimization service seam and contracts."""

from datetime import datetime, timedelta

import pytest

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.services import OptimizationService, ProgramService


class _StubBackend:
    def optimize(self, problem):
        return [1500.0, 2500.0, 3500.0, 4500.0]


def _build_forecast(start: datetime) -> ForecastBundle:
    timestamps = [start + timedelta(hours=i) for i in range(12)]
    values = [8000.0 + i * 100.0 for i in range(12)]
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


def test_optimization_returns_candidate_program_with_valid_schedule(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    program_service = ProgramService()
    service = OptimizationService(sample_reservoir_spec, program_service, backend=_StubBackend())

    forecast = _build_forecast(sample_initial_state.timestamp)
    program, schedule = service.optimize_flexible_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        horizon_hours=12,
        control_interval_seconds=3 * 3600,
        constraints={"max_outflow": 6000.0},
        objectives={"target_end_level": 165.0},
        directives={"safety_factor": 0.95},
    )

    assert len(program.module_sequence) == 1
    assert program.module_sequence[0].module_type == "flexible_release"
    assert schedule.control_interval_seconds == 3 * 3600
    assert schedule.segment_count == 4
    assert schedule.release_values == [1500.0, 2500.0, 3500.0, 4500.0]


def test_optimization_reports_pymoo_missing(
    sample_reservoir_spec,
    sample_initial_state,
    monkeypatch,
) -> None:
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)

    program_service = ProgramService()
    service = OptimizationService(sample_reservoir_spec, program_service, backend=_StubBackend())
    forecast = _build_forecast(sample_initial_state.timestamp)

    with pytest.raises(ValueError, match="install with `uv add pymoo`"):
        service.optimize_flexible_release_plan(
            initial_state=sample_initial_state,
            forecast=forecast,
            horizon_hours=12,
            control_interval_seconds=3 * 3600,
            optimizer_backend="pymoo",
        )
