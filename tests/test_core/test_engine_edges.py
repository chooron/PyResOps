"""Engine edge-case tests."""

from datetime import datetime

import pytest

from pyresops.core import SimulationEngine
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from pyresops.modules import ConstantReleaseModule, InflowLinearReleaseModule


def _make_program(**overrides):
    defaults = dict(
        id="edge_test",
        name="edge_test",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 3, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_release": 5000.0})
        ],
    )
    defaults.update(overrides)
    return DispatchProgram(**defaults)


def _make_forecast(timestamps, values):
    return ForecastBundle(
        forecast_time=datetime(2024, 7, 1, 0, 0, 0),
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


def test_no_inflow_series_raises(sample_reservoir_spec, sample_initial_state):
    engine = SimulationEngine(sample_reservoir_spec)
    program = _make_program()
    forecast = ForecastBundle(
        forecast_time=datetime(2024, 7, 1),
        series=[ForecastSeries(variable="rainfall", timestamps=[], values=[])],
    )
    with pytest.raises(ValueError, match="inflow"):
        engine.simulate(program, sample_initial_state, forecast, {})


def test_empty_module_sequence_defaults_to_inflow(sample_reservoir_spec, sample_initial_state, sample_forecast):
    engine = SimulationEngine(sample_reservoir_spec)
    program = _make_program(module_sequence=[])
    result = engine.simulate(program, sample_initial_state, sample_forecast, {})
    assert all(snapshot.outflow == snapshot.inflow for snapshot in result.snapshots)


def test_inflow_threshold_switch(sample_reservoir_spec, sample_initial_state):
    engine = SimulationEngine(sample_reservoir_spec)
    timestamps = [datetime(2024, 7, 1, hour, 0, 0) for hour in range(4)]
    forecast = _make_forecast(timestamps, [5000.0, 5000.0, 15000.0, 15000.0])
    program = _make_program(
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_release": 3000.0}),
            ModuleInstance(module_type="inflow_linear_release", parameters={"slope": 1.0}),
        ],
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="inflow_linear_release",
                condition_type="inflow_threshold",
                parameters={"threshold": 10000.0, "direction": "above"},
            )
        ],
    )
    modules = {
        "constant_release": ConstantReleaseModule({"target_release": 3000.0}),
        "inflow_linear_release": InflowLinearReleaseModule({"slope": 1.0}),
    }
    result = engine.simulate(program, sample_initial_state, forecast, modules)
    assert len(result.snapshots) == 4


def test_unknown_switch_condition_type_does_not_crash(
    sample_reservoir_spec, sample_initial_state, sample_forecast
):
    engine = SimulationEngine(sample_reservoir_spec)
    program = _make_program(
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="constant_release",
                condition_type="unknown_type",
                parameters={},
            )
        ]
    )
    modules = {"constant_release": ConstantReleaseModule({"target_release": 5000.0})}
    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
    assert len(result.snapshots) > 0
