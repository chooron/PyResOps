"""Fallback-stage tests for release family optimization."""

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


def _final_level_m(result) -> float:
    return float(result.selected_candidate.simulation_result.snapshots[-1].level)


def test_all_families_infeasible_fallback_selects_closest_target_level(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    forecast = _build_forecast(sample_initial_state.timestamp, [100.0] * 6)
    kwargs = {
        "initial_state": sample_initial_state,
        "forecast": forecast,
        "constraints": {"ecological_min_flow": 50.0, "max_release": 5000.0},
        "task_constraints": {"target_level": 150.0, "target_tolerance": 0.0},
    }

    expected_results = {}
    for module_type in DEFAULT_FAMILY_ORDER:
        service = OptimizationService(sample_reservoir_spec, ProgramService())
        expected_results[module_type] = service.optimize_release_plan(
            requested_module_type=module_type,
            **kwargs,
        )

    target_level = 150.0
    expected_module_type = min(
        DEFAULT_FAMILY_ORDER,
        key=lambda item: abs(_final_level_m(expected_results[item]) - target_level),
    )
    expected_gap = abs(_final_level_m(expected_results[expected_module_type]) - target_level)

    combined_service = OptimizationService(sample_reservoir_spec, ProgramService())
    combined = combined_service.optimize_release_plan(**kwargs)

    assert combined.fallback_applied is True
    assert combined.selected_candidate.feasible is False
    assert combined.selected_candidate.module_type == expected_module_type
    assert abs(_final_level_m(combined) - target_level) == pytest.approx(expected_gap)
    assert [item["module_type"] for item in combined.family_attempts] == list(DEFAULT_FAMILY_ORDER)


def test_all_fail_fallback_records_solver_metadata_for_each_family(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    service = OptimizationService(sample_reservoir_spec, ProgramService())
    forecast = _build_forecast(sample_initial_state.timestamp, [100.0] * 6)

    result = service.optimize_release_plan(
        initial_state=sample_initial_state,
        forecast=forecast,
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 150.0, "target_tolerance": 0.0},
    )

    assert result.fallback_applied is True
    assert [item["module_type"] for item in result.family_attempts] == list(DEFAULT_FAMILY_ORDER)
    assert all(item["candidate_count"] > 0 for item in result.family_attempts)
    assert all(str(item["solver_method"]).startswith("scipy.") for item in result.family_attempts)
