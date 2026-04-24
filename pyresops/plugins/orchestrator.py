"""Execution orchestration for plugins."""

from __future__ import annotations

from graphlib import TopologicalSorter
from typing import Any

from ..domain.forecast import ForecastBundle, ForecastSeries
from .models import (
    InputPluginContext,
    PluginExecutionResult,
    PluginSelectionConfig,
    PluginStage,
    PostPluginContext,
    ReportPluginContext,
    StepPluginContext,
)
from .registry import ExecutionPluginRegistry


class PluginOrchestrator:
    """Run execution plugins in a deterministic stage order."""

    def __init__(self, registry: ExecutionPluginRegistry):
        self.registry = registry

    def order_stage_plugins(
        self,
        selections: list[PluginSelectionConfig],
        *,
        plugin_kind: str,
    ) -> list[PluginSelectionConfig]:
        """Order selected plugins inside one stage using declared dependencies."""
        if not selections:
            return []
        name_to_selection = {selection.name: selection for selection in selections}
        graph: dict[str, set[str]] = {}
        for selection in selections:
            plugin = self.registry.get(plugin_kind, selection.name)
            graph[selection.name] = {
                dependency for dependency in plugin.depends_on if dependency in name_to_selection
            }
        sorter = TopologicalSorter(graph)
        return [name_to_selection[name] for name in sorter.static_order()]

    def prepare_forecast(
        self,
        *,
        forecast: ForecastBundle,
        initial_state,
        selection: PluginSelectionConfig | None,
    ) -> tuple[ForecastBundle, PluginExecutionResult | None]:
        """Execute the configured input plugin, if any."""
        if selection is None:
            return forecast, None
        plugin = self.registry.get("input", selection.name)
        normalized_config = plugin.validate_config(selection.config)
        context = InputPluginContext(forecast=forecast, initial_state=initial_state)
        plugin.validate_inputs(context)
        result = plugin.execute(context, normalized_config)
        generated_series = result.payload.get("generated_series")
        if not isinstance(generated_series, dict):
            raise ValueError(f"Input plugin '{selection.name}' did not return generated_series")
        updated_forecast = self._replace_forecast_series(forecast, generated_series)
        return updated_forecast, result

    def execute_step(
        self,
        *,
        selection: PluginSelectionConfig | None,
        context: StepPluginContext,
    ) -> PluginExecutionResult | None:
        """Execute one configured step plugin."""
        if selection is None:
            return None
        plugin = self.registry.get("step", selection.name)
        normalized_config = plugin.validate_config(selection.config)
        plugin.validate_inputs(context)
        return plugin.execute(context, normalized_config)

    def execute_post(
        self,
        *,
        selection: PluginSelectionConfig | None,
        context: PostPluginContext,
    ) -> PluginExecutionResult | None:
        """Execute one configured post plugin."""
        if selection is None:
            return None
        plugin = self.registry.get("post", selection.name)
        normalized_config = plugin.validate_config(selection.config)
        plugin.validate_inputs(context)
        return plugin.execute(context, normalized_config)

    def execute_report(
        self,
        *,
        selection: PluginSelectionConfig | None,
        context: ReportPluginContext,
    ) -> PluginExecutionResult | None:
        """Execute one configured report plugin."""
        if selection is None:
            return None
        plugin = self.registry.get("report", selection.name)
        normalized_config = plugin.validate_config(selection.config)
        plugin.validate_inputs(context)
        return plugin.execute(context, normalized_config)

    @staticmethod
    def stage_for_kind(plugin_kind: str) -> PluginStage:
        """Return the default stage for one plugin kind."""
        mapping = {
            "input": PluginStage.INFLOW_GENERATION,
            "step": PluginStage.DISPATCH_STEP,
            "post": PluginStage.POST_SIMULATION,
            "report": PluginStage.REPORT_GENERATION,
        }
        return mapping[plugin_kind]

    def _replace_forecast_series(
        self,
        forecast: ForecastBundle,
        series_payload: dict[str, Any],
    ) -> ForecastBundle:
        variable = str(series_payload.get("variable", "inflow"))
        generated_series = ForecastSeries(**series_payload)
        remaining = [series for series in forecast.series if series.variable != variable]
        remaining.append(generated_series)
        return ForecastBundle(
            forecast_time=forecast.forecast_time,
            series=remaining,
            metadata=dict(forecast.metadata),
        )
