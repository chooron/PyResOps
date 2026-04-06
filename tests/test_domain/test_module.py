"""Tests for operation modules."""

import pytest

from pyresops.modules import ConstantReleaseModule, InflowDrivenModule, StorageDrivenModule


def test_constant_release_module(sample_reservoir_spec, sample_initial_state):
    """测试恒定下泄模块."""
    module = ConstantReleaseModule(parameters={"target_flow": 5000.0})

    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)

    assert outflow == pytest.approx(5000.0)


def test_constant_release_module_validation():
    """测试恒定下泄模块参数验证."""
    with pytest.raises(ValueError):
        ConstantReleaseModule(parameters={})


def test_inflow_driven_module(sample_reservoir_spec, sample_initial_state):
    """测试入流驱动模块."""
    module = InflowDrivenModule(parameters={"coefficient": 1.2})

    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)

    assert outflow == pytest.approx(9600.0)


def test_inflow_driven_module_default(sample_reservoir_spec, sample_initial_state):
    """测试入流驱动模块默认参数."""
    module = InflowDrivenModule(parameters={})

    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)

    assert outflow == pytest.approx(8000.0)


def test_storage_driven_module(sample_reservoir_spec, sample_initial_state):
    """测试蓄水量驱动模块."""
    module = StorageDrivenModule(
        parameters={
            "low_storage_threshold": 0.3,
            "high_storage_threshold": 0.8,
            "base_flow": 3000.0,
        }
    )

    outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)

    # 当前库容: 30.0 / 39.3 ≈ 0.76, 介于阈值之间
    assert outflow > 3000.0
