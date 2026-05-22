"""Shared helpers for plugin demos."""

from __future__ import annotations

from datetime import datetime, timedelta

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
    ReservoirState,
)


def build_demo_spec() -> ReservoirSpec:
    """Build a small demo reservoir spec."""
    return ReservoirSpec(
        id="demo_reservoir",
        name="Demo Reservoir",
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


def build_demo_state(timestamp: datetime | None = None) -> ReservoirState:
    """Build a demo reservoir state."""
    spec = build_demo_spec()
    ts = timestamp or datetime(2024, 7, 1, 0, 0, 0)
    level = 165.0
    storage = spec.level_storage_curve.get_storage(level)
    return ReservoirState(
        timestamp=ts,
        level=level,
        storage=storage,
        inflow=8000.0,
        outflow=8000.0,
    )


def build_rainfall_forecast(step_count: int = 6) -> ForecastBundle:
    """Build a demo rainfall-only forecast."""
    timestamps = [datetime(2024, 7, 1, 0, 0, 0) + timedelta(hours=index) for index in range(step_count)]
    values = [15.0, 25.0, 20.0, 10.0, 5.0, 0.0][:step_count]
    return ForecastBundle(
        forecast_time=timestamps[0],
        series=[
            ForecastSeries(
                variable="rainfall",
                timestamps=timestamps,
                values=values,
                unit="mm/h",
            )
        ],
    )


def build_outflow_forecast(step_count: int = 6) -> ForecastBundle:
    """Build a demo inflow forecast for the simulation path."""
    timestamps = [datetime(2024, 7, 1, 0, 0, 0) + timedelta(hours=index) for index in range(step_count)]
    values = [6000.0, 6500.0, 7000.0, 6800.0, 6200.0, 5500.0][:step_count]
    return ForecastBundle(
        forecast_time=timestamps[0],
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=timestamps,
                values=values,
                unit="m3/s",
            )
        ],
    )
