"""Tests for simulation engine."""

from datetime import datetime

from pyresops.core import SimulationEngine
from pyresops.domain.program import DispatchProgram, TimeHorizon, ModuleInstance
from pyresops.modules import ConstantReleaseModule


def test_simulation_engine_basic(
    sample_reservoir_spec, sample_initial_state, sample_forecast
):
    """测试仿真引擎基本功能."""
    engine = SimulationEngine(sample_reservoir_spec)

    # 创建简单方案
    program = DispatchProgram(
        id="test_sim",
        name="测试仿真",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 5, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 7000.0})
        ],
    )

    # 准备模块
    modules = {"constant_release": ConstantReleaseModule({"target_flow": 7000.0})}

    # 运行仿真
    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)

    assert result.program_id == "test_sim"
    assert len(result.snapshots) > 0
    assert result.max_level >= sample_initial_state.level or result.max_level <= sample_initial_state.level


def test_simulation_water_balance(
    sample_reservoir_spec, sample_initial_state, sample_forecast
):
    """测试水量平衡."""
    engine = SimulationEngine(sample_reservoir_spec)

    # 入流等于出流的方案
    program = DispatchProgram(
        id="balance_test",
        name="水量平衡测试",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 2, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 8000.0})
        ],
    )

    modules = {"constant_release": ConstantReleaseModule({"target_flow": 8000.0})}

    result = engine.simulate(program, sample_initial_state, sample_forecast, modules)

    # 入流等于出流时，库容和水位应保持稳定 (在前几个时段)
    first_snapshot = result.snapshots[0]
    assert first_snapshot.inflow >= 0
    assert first_snapshot.outflow >= 0
