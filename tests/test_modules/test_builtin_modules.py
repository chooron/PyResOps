"""Tests for built-in operation modules."""

import pytest

from pyresops.modules import ConstantReleaseModule, InflowDrivenModule, StorageDrivenModule


def test_constant_release_info():
    """测试恒定下泄模块元信息."""
    info = ConstantReleaseModule.get_info()

    assert info.module_type == "constant_release"
    assert info.name == "恒定下泄"
    assert "target_flow" in info.parameters_schema["properties"]


def test_inflow_driven_info():
    """测试入流驱动模块元信息."""
    info = InflowDrivenModule.get_info()

    assert info.module_type == "inflow_driven"
    assert info.name == "入流驱动"


def test_storage_driven_info():
    """测试蓄水量驱动模块元信息."""
    info = StorageDrivenModule.get_info()

    assert info.module_type == "storage_driven"
    assert info.name == "蓄水量驱动"


def test_all_modules_have_unique_types():
    """测试所有模块类型唯一."""
    modules = [ConstantReleaseModule, InflowDrivenModule, StorageDrivenModule]
    types = [m.get_info().module_type for m in modules]

    assert len(types) == len(set(types))
