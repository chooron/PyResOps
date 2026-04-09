"""Plugin registry."""

from __future__ import annotations

from ..constraints import ConstraintRegistry
from ..metrics import MetricRegistry
from ..rules import RuleRegistry
from .base import PluginBase


class PluginRegistry:
    """插件注册表 (Plugin Registry)."""

    def __init__(self):
        """初始化注册表."""
        self._plugins: dict[str, PluginBase] = {}
        self._constraint_registry = ConstraintRegistry()
        self._rule_registry = RuleRegistry()
        self._metric_registry = MetricRegistry()

    def register(self, plugin: PluginBase) -> None:
        """注册插件."""
        name = plugin.get_name()
        self._plugins[name] = plugin
        plugin.initialize()

        register_constraints = getattr(plugin, "register_constraints", None)
        if callable(register_constraints):
            register_constraints(self._constraint_registry)

        register_rules = getattr(plugin, "register_rules", None)
        if callable(register_rules):
            register_rules(self._rule_registry)

        register_metrics = getattr(plugin, "register_metrics", None)
        if callable(register_metrics):
            register_metrics(self._metric_registry)

    def get_plugin(self, name: str) -> PluginBase | None:
        """获取插件."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """列出所有插件."""
        return list(self._plugins.keys())

    def get_constraint_registry(self) -> ConstraintRegistry:
        """Get merged constraint registry from plugins."""
        return self._constraint_registry

    def get_rule_registry(self) -> RuleRegistry:
        """Get merged rule registry from plugins."""
        return self._rule_registry

    def get_metric_registry(self) -> MetricRegistry:
        """Get merged metric registry from plugins."""
        return self._metric_registry
