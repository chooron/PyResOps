"""Extreme input tests for the new release taxonomy."""

from datetime import datetime

from pyresops.core import SimulationEngine
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
from pyresops.modules import (
    ConstantReleaseModule,
    InflowLinearReleaseModule,
    StoragePiecewiseConstantReleaseModule,
)


def _spec():
    from pyresops.domain.reservoir import DischargeCapacity, LevelStorageCurve, ReservoirSpec

    return ReservoirSpec(
        id="extreme",
        name="extreme",
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


def _state(level, inflow):
    from pyresops.domain.reservoir import ReservoirState

    spec = _spec()
    storage = spec.level_storage_curve.get_storage(level)
    return ReservoirState(
        timestamp=datetime(2024, 7, 1),
        level=level,
        storage=storage,
        inflow=inflow,
        outflow=inflow,
    )


def _forecast(values):
    timestamps = [datetime(2024, 7, 1, hour, 0, 0) for hour in range(len(values))]
    return ForecastBundle(
        forecast_time=datetime(2024, 7, 1),
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


def test_constant_release_zero_inflow():
    spec = _spec()
    engine = SimulationEngine(spec)
    state = _state(165.0, 0.0)
    program = DispatchProgram(
        id="zero",
        name="zero",
        time_horizon=TimeHorizon(start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 2, 0, 0), time_step=3600),
        module_sequence=[ModuleInstance(module_type="constant_release", parameters={"target_release": 5000.0})],
    )
    result = engine.simulate(
        program,
        state,
        _forecast([0.0, 0.0, 0.0]),
        {"constant_release": ConstantReleaseModule({"target_release": 5000.0})},
    )
    assert result.min_level < 165.0


def test_inflow_linear_release_zero_inflow():
    spec = _spec()
    engine = SimulationEngine(spec)
    state = _state(165.0, 0.0)
    program = DispatchProgram(
        id="zero_linear",
        name="zero_linear",
        time_horizon=TimeHorizon(start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 2, 0, 0), time_step=3600),
        module_sequence=[ModuleInstance(module_type="inflow_linear_release", parameters={"slope": 1.0})],
    )
    result = engine.simulate(
        program,
        state,
        _forecast([0.0, 0.0, 0.0]),
        {"inflow_linear_release": InflowLinearReleaseModule({"slope": 1.0})},
    )
    assert all(snapshot.outflow == 0.0 for snapshot in result.snapshots)


def test_storage_piecewise_release_at_low_storage():
    spec = _spec()
    state = _state(145.0, 8000.0)
    module = StoragePiecewiseConstantReleaseModule(
        {"metric": "storage_ratio", "breakpoints": [0.3, 0.8], "release_values": [3000.0, 5000.0, 9000.0]}
    )
    outflow = module.compute_outflow(state, spec, 8000.0)
    assert outflow == 3000.0
