"""Tests for the new execution plugin registry."""

from __future__ import annotations

from pyresops.plugins import ExecutionPluginRegistry, InputPluginBase, PluginExecutionResult
from pyresops.plugins.models import BasePluginContext, PluginStage


class _DummyInputPlugin(InputPluginBase):
    plugin_name = "dummy_input"
    stage = PluginStage.INFLOW_GENERATION
    summary = "Dummy input plugin"

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        return dict(config)

    def execute(
        self,
        context: BasePluginContext,
        config: dict[str, object],
    ) -> PluginExecutionResult:
        return PluginExecutionResult(payload={"ok": True}, used_config=dict(config))


def test_execution_registry_register_get_and_describe() -> None:
    registry = ExecutionPluginRegistry()
    plugin = _DummyInputPlugin()

    registry.register(plugin)

    assert registry.get("input", "dummy_input") is plugin
    listed = registry.list("input")
    assert listed == [
        {
            "plugin_kind": "input",
            "plugin_type": "input",
            "plugin_name": "dummy_input",
            "summary": "Dummy input plugin",
            "stage": PluginStage.INFLOW_GENERATION,
        }
    ]
    descriptor = registry.describe_all()[0]
    assert descriptor["plugin_name"] == "dummy_input"
    assert descriptor["plugin_kind"] == "input"
    assert descriptor["plugin_type"] == "input"
