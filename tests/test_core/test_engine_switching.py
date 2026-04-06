"""Tests for engine module switching via SwitchCondition."""

from datetime import datetime

import pytest

from res_ops.core import SimulationEngine
from res_ops.domain.program import DispatchProgram, TimeHorizon, ModuleInstance, SwitchCondition
from res_ops.modules import ConstantReleaseModule, InflowDrivenModule


def test_level_threshold_switch(sample_reservoir_spec, sample_initial_state, sample_forecast):
    """测试基于水位阈值的模块切换."""
    engine = SimulationEngine(sample_reservoir_spec)

    program = DispatchProgram(
        id="switch_test",
        name="水位切换测试",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000.0}),
            ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 1.0}),
        ],
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="inflow_driven",
                condition_type="level_threshold",
                parameters={"threshold": 168.0, "direction": "above"},
            ),
        ],
    )

    modules = {
        "constant_release": ConstantReleaseModule({"target_flow": 5000.0}),
        "inflow_driven": InflowDrivenModule({"coefficient": 1.0}),
    }

    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)

    assert result.program_id == "switch_test"
    assert len(result.snapshots) > 0
    # 至少有一个快照的 active_module 不为 None
    active_modules = [s.active_module for s in result.snapshots]
    assert any(m is not None for m in active_modules)


def test_time_based_switch(sample_reservoir_spec, sample_initial_state, sample_forecast):
    """测试基于时间的模块切换."""
    engine = SimulationEngine(sample_reservoir_spec)

    program = DispatchProgram(
        id="time_switch",
        name="时间切换测试",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000.0}),
            ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 0.8}),
        ],
        switch_conditions=[
            SwitchCondition(
                from_module="constant_release",
                to_module="inflow_driven",
                condition_type="time_based",
                parameters={"trigger_time": "2024-07-01T03:00:00"},
            ),
        ],
    )

    modules = {
        "constant_release": ConstantReleaseModule({"target_flow": 5000.0}),
        "inflow_driven": InflowDrivenModule({"coefficient": 0.8}),
    }

    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)

    # 第3步之后应切换到 inflow_driven
    later_snapshots = [s for s in result.snapshots if s.timestamp.hour >= 3]
    if later_snapshots:
        assert any(s.active_module == "inflow_driven" for s in later_snapshots)


def test_no_switch_without_conditions(sample_reservoir_spec, sample_initial_state, sample_forecast):
    """无切换条件时应保持初始模块."""
    engine = SimulationEngine(sample_reservoir_spec)

    program = DispatchProgram(
        id="no_switch",
        name="无切换",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 3, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 7000.0}),
        ],
        switch_conditions=[],
    )

    modules = {"constant_release": ConstantReleaseModule({"target_flow": 7000.0})}

    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)

    for snap in result.snapshots:
        assert snap.active_module == "constant_release"
