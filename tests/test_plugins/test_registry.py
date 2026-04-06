"""Plugin registry complete tests."""

import pytest

from pyresops.plugins.base import PluginBase
from pyresops.plugins.registry import PluginRegistry


class DummyPlugin(PluginBase):
    """测试用插件."""

    def __init__(self, name: str):
        self._name = name
        self._initialized = False

    def initialize(self) -> None:
        self._initialized = True

    def get_name(self) -> str:
        return self._name


class TestPluginRegistry:
    def test_register_and_get(self):
        reg = PluginRegistry()
        plugin = DummyPlugin("test_plugin")
        reg.register(plugin)

        assert plugin._initialized  # register 触发 initialize
        assert reg.get_plugin("test_plugin") is plugin

    def test_get_nonexistent(self):
        reg = PluginRegistry()
        assert reg.get_plugin("nope") is None

    def test_list_plugins(self):
        reg = PluginRegistry()
        reg.register(DummyPlugin("a"))
        reg.register(DummyPlugin("b"))
        names = reg.list_plugins()
        assert "a" in names
        assert "b" in names
        assert len(names) == 2

    def test_duplicate_register_overwrites(self):
        reg = PluginRegistry()
        p1 = DummyPlugin("dup")
        p2 = DummyPlugin("dup")
        reg.register(p1)
        reg.register(p2)
        assert reg.get_plugin("dup") is p2

    def test_empty_registry(self):
        reg = PluginRegistry()
        assert reg.list_plugins() == []
        assert reg.get_plugin("any") is None


class TestPluginBaseAbstract:
    """验证 PluginBase 是抽象类"""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            PluginBase()
