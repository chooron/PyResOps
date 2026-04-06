"""Tests for program domain objects."""

from datetime import datetime

from res_ops.domain.program import TimeHorizon, ModuleInstance, DispatchProgram


def test_time_horizon():
    """测试调度时段."""
    horizon = TimeHorizon(
        start=datetime(2024, 7, 1, 0, 0, 0),
        end=datetime(2024, 7, 2, 0, 0, 0),
        time_step=3600,
    )

    assert horizon.total_steps() == 24


def test_module_instance():
    """测试模块实例."""
    module = ModuleInstance(
        module_type="constant_release",
        parameters={"target_flow": 5000.0},
    )

    assert module.module_type == "constant_release"
    assert module.parameters["target_flow"] == 5000.0


def test_dispatch_program():
    """测试调度方案."""
    horizon = TimeHorizon(
        start=datetime(2024, 7, 1, 0, 0, 0),
        end=datetime(2024, 7, 2, 0, 0, 0),
        time_step=3600,
    )

    program = DispatchProgram(
        id="test_program",
        name="测试方案",
        time_horizon=horizon,
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000.0})
        ],
    )

    assert program.id == "test_program"
    assert len(program.module_sequence) == 1
