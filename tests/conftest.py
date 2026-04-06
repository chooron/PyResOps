"""Pytest fixtures for testing."""

from datetime import datetime

import pytest

from pyresops.domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
    ReservoirState,
)
from pyresops.domain.forecast import ForecastBundle, ForecastSeries


@pytest.fixture
def sample_reservoir_spec() -> ReservoirSpec:
    """创建示例水库规范."""
    return ReservoirSpec(
        id="test_reservoir",
        name="测试水库",
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


@pytest.fixture
def sample_initial_state() -> ReservoirState:
    """创建示例初始状态."""
    return ReservoirState(
        timestamp=datetime(2024, 7, 1, 0, 0, 0),
        level=165.0,
        storage=30.0,
        inflow=8000.0,
        outflow=8000.0,
    )


@pytest.fixture
def sample_forecast() -> ForecastBundle:
    """创建示例预报数据."""
    timestamps = [datetime(2024, 7, 1, i, 0, 0) for i in range(24)]
    inflow_values = [8000.0 + 500.0 * i for i in range(24)]

    return ForecastBundle(
        forecast_time=datetime(2024, 7, 1, 0, 0, 0),
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=timestamps,
                values=inflow_values,
                unit="m³/s",
            )
        ],
    )
