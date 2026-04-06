"""Tests for hydraulics calculations."""

import pytest

from res_ops.core import HydraulicsCalculator


def test_hydraulics_level_storage(sample_reservoir_spec):
    """测试水位-库容计算."""
    hydraulics = HydraulicsCalculator(sample_reservoir_spec)

    storage = hydraulics.compute_storage_from_level(165.0)
    assert storage == pytest.approx(30.0)

    level = hydraulics.compute_level_from_storage(30.0)
    assert level == pytest.approx(165.0)


def test_hydraulics_discharge_capacity(sample_reservoir_spec):
    """测试泄流能力计算."""
    hydraulics = HydraulicsCalculator(sample_reservoir_spec)

    max_discharge = hydraulics.compute_max_discharge(165.0)
    assert max_discharge == pytest.approx(15000.0)


def test_hydraulics_water_balance(sample_reservoir_spec, sample_initial_state):
    """测试水量平衡推进."""
    hydraulics = HydraulicsCalculator(sample_reservoir_spec)

    # 入流大于出流
    next_state = hydraulics.water_balance_step(sample_initial_state, 10000.0, 8000.0, 3600)

    # 库容应增加
    assert next_state.storage > sample_initial_state.storage
    assert next_state.level > sample_initial_state.level


def test_hydraulics_validate_outflow(sample_reservoir_spec):
    """测试出库流量校核."""
    hydraulics = HydraulicsCalculator(sample_reservoir_spec)

    # 合法流量
    is_valid, adjusted = hydraulics.validate_outflow(165.0, 10000.0)
    assert is_valid
    assert adjusted == pytest.approx(10000.0)

    # 超过泄流能力
    is_valid, adjusted = hydraulics.validate_outflow(165.0, 20000.0)
    assert not is_valid
    assert adjusted == pytest.approx(15000.0)

    # 负流量
    is_valid, adjusted = hydraulics.validate_outflow(165.0, -100.0)
    assert not is_valid
    assert adjusted == pytest.approx(0.0)
