"""Tests for reservoir domain objects."""

import pytest

from res_ops.domain.reservoir import LevelStorageCurve, DischargeCapacity


def test_level_storage_curve():
    """测试水位-库容曲线."""
    curve = LevelStorageCurve(
        levels=[100.0, 110.0, 120.0],
        storages=[0.0, 10.0, 25.0],
    )

    # 测试插值
    assert curve.get_storage(100.0) == pytest.approx(0.0)
    assert curve.get_storage(110.0) == pytest.approx(10.0)
    assert curve.get_storage(105.0) == pytest.approx(5.0)

    # 测试反向插值
    assert curve.get_level(0.0) == pytest.approx(100.0)
    assert curve.get_level(10.0) == pytest.approx(110.0)
    assert curve.get_level(5.0) == pytest.approx(105.0)


def test_level_storage_curve_validation():
    """测试水位-库容曲线验证."""
    with pytest.raises(ValueError):
        LevelStorageCurve(
            levels=[100.0, 90.0, 110.0],  # 非递增
            storages=[0.0, 10.0, 20.0],
        )


def test_discharge_capacity():
    """测试泄流能力曲线."""
    capacity = DischargeCapacity(
        levels=[100.0, 110.0, 120.0],
        max_discharges=[0.0, 5000.0, 10000.0],
    )

    assert capacity.get_max_discharge(100.0) == pytest.approx(0.0)
    assert capacity.get_max_discharge(110.0) == pytest.approx(5000.0)
    assert capacity.get_max_discharge(105.0) == pytest.approx(2500.0)


def test_reservoir_spec(sample_reservoir_spec):
    """测试水库规范."""
    assert sample_reservoir_spec.id == "test_reservoir"
    assert sample_reservoir_spec.normal_level == 175.0
    assert sample_reservoir_spec.validate_level_range(165.0)
    assert not sample_reservoir_spec.validate_level_range(200.0)
