"""Tests for engine module switching via SwitchCondition."""

from datetime import datetime

from pyresops.core import SimulationEngine
from pyresops.domain.program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from pyresops.modules import ConstantReleaseModule, InflowLinearReleaseModule


def test_level_threshold_switch(sample_reservoir_spec, sample_initial_state, sample_forecast):
    engine = SimulationEngine(sample_reservoir_spec)
    program = DispatchProgram(
        id="switch_test",
        name="switch_test",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_release": 5000.0}),
            ModuleInstance(module_type="inflow_linear_release", parameters={"slope": 1.0}),
        ],
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="inflow_linear_release",
                condition_type="level_threshold",
                parameters={"threshold": 168.0, "direction": "above"},
            )
        ],
    )
    modules = {
        "constant_release": ConstantReleaseModule({"target_release": 5000.0}),
        "inflow_linear_release": InflowLinearReleaseModule({"slope": 1.0}),
    }
    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
    assert result.program_id == "switch_test"
    assert any(snapshot.active_module is not None for snapshot in result.snapshots)


def test_time_based_switch(sample_reservoir_spec, sample_initial_state, sample_forecast):
    engine = SimulationEngine(sample_reservoir_spec)
    program = DispatchProgram(
        id="time_switch",
        name="time_switch",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_release": 5000.0}),
            ModuleInstance(module_type="inflow_linear_release", parameters={"slope": 0.8}),
        ],
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="inflow_linear_release",
                condition_type="time_based",
                parameters={"trigger_time": "2024-07-01T03:00:00"},
            )
        ],
    )
    modules = {
        "constant_release": ConstantReleaseModule({"target_release": 5000.0}),
        "inflow_linear_release": InflowLinearReleaseModule({"slope": 0.8}),
    }
    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
    later_snapshots = [snapshot for snapshot in result.snapshots if snapshot.timestamp.hour >= 3]
    assert any(snapshot.active_module == "inflow_linear_release" for snapshot in later_snapshots)


def test_no_switch_without_conditions(sample_reservoir_spec, sample_initial_state, sample_forecast):
    engine = SimulationEngine(sample_reservoir_spec)
    program = DispatchProgram(
        id="no_switch",
        name="no_switch",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 3, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_release": 7000.0}),
        ],
    )
    modules = {"constant_release": ConstantReleaseModule({"target_release": 7000.0})}
    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
    assert all(snapshot.active_module == "constant_release" for snapshot in result.snapshots)
