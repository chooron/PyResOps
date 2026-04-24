"""Optimization tests for the six base release families."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.services import OptimizationService, ProgramService
from pyresops.services.optimization import DEFAULT_FAMILY_ORDER


def _build_forecast(start: datetime, values: list[float]) -> ForecastBundle:
    timestamps = [start + timedelta(hours=index) for index in range(len(values))]
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


@pytest.mark.parametrize("module_type", DEFAULT_FAMILY_ORDER)
def test_each_release_family_reports_true_when_target_is_reachable(
    sample_reservoir_spec,
    sample_initial_state,
    module_type: str,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    forecast = _build_forecast(sample_initial_state.timestamp, [4000.0] * 6)

    result = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 165.0, "target_tolerance": 0.2},
        requested_module_type=module_type,
    )

    payload = result.to_dict()
    assert result.selected_candidate.module_type == module_type
    assert result.selected_candidate.feasible is True
    assert result.fallback_applied is False
    assert payload["feasible_solution_found"] is True
    assert [item["module_type"] for item in result.family_attempts] == [module_type]


@pytest.mark.parametrize("module_type", DEFAULT_FAMILY_ORDER)
def test_each_release_family_reports_false_when_target_is_unreachable(
    sample_reservoir_spec,
    sample_initial_state,
    module_type: str,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    forecast = _build_forecast(sample_initial_state.timestamp, [100.0] * 6)

    result = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 150.0, "target_tolerance": 0.0},
        requested_module_type=module_type,
    )

    payload = result.to_dict()
    assert result.selected_candidate.module_type == module_type
    assert result.selected_candidate.feasible is False
    assert result.fallback_applied is True
    assert payload["feasible_solution_found"] is False
    assert result.family_attempts[0]["selected_candidate"]["feasible"] is False
