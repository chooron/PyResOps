"""Tests for stage ordering and resolution in the new plugin framework."""

from __future__ import annotations

from datetime import datetime, timedelta

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.plugins import (
    ExecutionPluginRegistry,
    PluginBundleConfig,
    PluginManager,
    PluginOrchestrator,
    PluginSelectionConfig,
    StepPluginBase,
)
from pyresops.plugins.models import BasePluginContext, PluginExecutionResult


class _BaseStepPlugin(StepPluginBase):
    summary = "step plugin"

    def validate_config(self, config: dict[str, object]) -> dict[str, object]:
        return dict(config)

    def execute(
        self,
        context: BasePluginContext,
        config: dict[str, object],
    ) -> PluginExecutionResult:
        return PluginExecutionResult(payload={"plugin": self.plugin_name})


class _UpstreamStepPlugin(_BaseStepPlugin):
    plugin_name = "upstream"
    depends_on = []


class _DownstreamStepPlugin(_BaseStepPlugin):
    plugin_name = "downstream"
    depends_on = ["upstream"]


def test_orchestrator_orders_stage_plugins_by_dependency() -> None:
    registry = ExecutionPluginRegistry()
    registry.register(_UpstreamStepPlugin())
    registry.register(_DownstreamStepPlugin())
    orchestrator = PluginOrchestrator(registry)

    ordered = orchestrator.order_stage_plugins(
        [
            PluginSelectionConfig(name="downstream"),
            PluginSelectionConfig(name="upstream"),
        ],
        plugin_kind="step",
    )

    assert [item.name for item in ordered] == ["upstream", "downstream"]


def test_plugin_bundle_uses_step_and_post_keys() -> None:
    bundle = PluginBundleConfig(
        step={"name": "gate_release_calculator", "config": {"gate_opening": 0.2}},
        post={"name": "muskingum_routing", "config": {"k": 3.0, "x": 0.2, "dt_hours": 1.0}},
    )

    assert bundle.step is not None
    assert bundle.step.name == "gate_release_calculator"
    assert bundle.post is not None
    assert bundle.post.name == "muskingum_routing"


def test_plugin_manager_resolves_unique_input_plugin_for_rainfall_only_forecast() -> None:
    manager = PluginManager()
    timestamps = [datetime(2024, 7, 1) + timedelta(hours=index) for index in range(4)]
    forecast = ForecastBundle(
        forecast_time=timestamps[0],
        series=[
            ForecastSeries(
                variable="rainfall",
                timestamps=timestamps,
                values=[10.0, 20.0, 10.0, 0.0],
                unit="mm/h",
            )
        ],
    )

    result = manager.resolve_plugins_for_task(forecast=forecast)

    assert result.status == "executable"
    assert result.selected["input"] == "simple_rainfall_runoff"
