"""Plugin registry."""

from __future__ import annotations

from collections import defaultdict

from ..constraints import ConstraintRegistry
from ..metrics import MetricRegistry
from ..rules import RuleRegistry
from .base import ExecutionPluginBase, PluginBase
from .models import PluginKind, PluginStage


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


class ExecutionPluginRegistry:
    """Typed registry for execution plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, dict[str, ExecutionPluginBase]] = defaultdict(dict)

    def register(self, plugin: ExecutionPluginBase) -> None:
        """Register or replace one execution plugin."""
        self._plugins[plugin.plugin_kind][plugin.plugin_name] = plugin

    def get(self, plugin_kind: PluginKind, plugin_name: str) -> ExecutionPluginBase:
        """Get a plugin or raise a readable error."""
        plugin = self._plugins.get(plugin_kind, {}).get(plugin_name)
        if plugin is None:
            available = sorted(self._plugins.get(plugin_kind, {}).keys())
            raise KeyError(
                f"Unknown {plugin_kind} plugin '{plugin_name}'. Available: {available or 'none'}"
            )
        return plugin

    def list(self, plugin_kind: PluginKind | None = None) -> list[dict[str, str]]:
        """List registered execution plugins."""
        kinds = [plugin_kind] if plugin_kind else sorted(self._plugins.keys())
        items: list[dict[str, str]] = []
        for current_kind in kinds:
            for _, plugin in sorted(self._plugins.get(current_kind, {}).items()):
                items.append(
                    {
                        "plugin_kind": current_kind,
                        "plugin_type": current_kind,
                        "plugin_name": plugin.plugin_name,
                        "summary": plugin.summary,
                        "stage": plugin.stage,
                    }
                )
        return items

    def list_by_stage(self, stage: PluginStage) -> list[ExecutionPluginBase]:
        """List all plugins registered for one stage."""
        matched: list[ExecutionPluginBase] = []
        for plugins_by_name in self._plugins.values():
            for plugin in plugins_by_name.values():
                if plugin.stage == stage:
                    matched.append(plugin)
        return sorted(matched, key=lambda item: item.plugin_name)

    def describe_all(self) -> list[dict[str, object]]:
        """Return manifests for every registered plugin."""
        items: list[dict[str, object]] = []
        for kind in sorted(self._plugins.keys()):
            for _, plugin in sorted(self._plugins[kind].items()):
                items.append(plugin.describe())
        return items
