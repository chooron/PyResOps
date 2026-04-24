"""Top-level plugin manager for execution plugins."""

from __future__ import annotations

from typing import Any

from ..domain.forecast import ForecastBundle
from ..domain.reservoir import ReservoirState
from .builtin import register_builtin_plugins
from .loader import PluginLoader
from .models import (
    PluginBundleConfig,
    PluginExecutionResult,
    PluginResolutionResult,
    PluginSelectionConfig,
    PostPluginContext,
    ReportPluginContext,
    StepPluginContext,
)
from .orchestrator import PluginOrchestrator
from .registry import ExecutionPluginRegistry
from .resolver import PluginResolver


class PluginManager:
    """Coordinates registry, loading, resolution, and execution summaries."""

    def __init__(self, registry: ExecutionPluginRegistry | None = None) -> None:
        self.registry = registry or ExecutionPluginRegistry()
        self.loader = PluginLoader(self.registry)
        self.resolver = PluginResolver(self.registry)
        self.orchestrator = PluginOrchestrator(self.registry)
        if not self.registry.describe_all():
            register_builtin_plugins(self.registry)

    def prepare_forecast(
        self,
        *,
        forecast: ForecastBundle,
        initial_state: ReservoirState | None,
        plugin_bundle: PluginBundleConfig | None,
    ) -> tuple[ForecastBundle, dict[str, Any], PluginBundleConfig | None]:
        """Run the configured input plugin once and return the updated forecast."""
        if plugin_bundle is None or plugin_bundle.input is None:
            return forecast, {}, plugin_bundle

        updated_forecast, result = self.orchestrator.prepare_forecast(
            forecast=forecast,
            initial_state=initial_state,
            selection=plugin_bundle.input,
        )
        next_bundle = plugin_bundle.without_input()
        packed = {} if result is None else {"input": self._pack_result(plugin_bundle.input, result)}
        return updated_forecast, packed, next_bundle

    def execute_step(
        self,
        *,
        selection: PluginSelectionConfig | None,
        context: StepPluginContext,
    ) -> PluginExecutionResult | None:
        """Execute one step plugin."""
        return self.orchestrator.execute_step(selection=selection, context=context)


    def execute_post(
        self,
        *,
        selection: PluginSelectionConfig | None,
        context: PostPluginContext,
    ) -> PluginExecutionResult | None:
        """Execute one post plugin."""
        return self.orchestrator.execute_post(selection=selection, context=context)

    def execute_report(
        self,
        *,
        selection: PluginSelectionConfig | None,
        context: ReportPluginContext,
    ) -> PluginExecutionResult | None:
        """Execute one report plugin."""
        return self.orchestrator.execute_report(selection=selection, context=context)


    def describe_all(self) -> list[dict[str, object]]:
        """Return all plugin manifests."""
        return self.registry.describe_all()

    def describe_plugin(self, *, plugin_kind: str, plugin_name: str) -> dict[str, Any]:
        """Describe one plugin."""
        return self.registry.get(plugin_kind, plugin_name).describe()

    def resolve_plugins_for_task(
        self,
        *,
        forecast: ForecastBundle | None = None,
        plugin_bundle: PluginBundleConfig | None = None,
        requested_capabilities: list[str] | None = None,
    ) -> PluginResolutionResult:
        """Resolve plugin recommendations for the given task."""
        return self.resolver.resolve_for_task(
            forecast=forecast,
            plugin_bundle=plugin_bundle,
            requested_capabilities=requested_capabilities,
        )

    def pack_selection_result(
        self,
        *,
        selection: PluginSelectionConfig,
        result: PluginExecutionResult,
    ) -> dict[str, Any]:
        """Pack one result for service/MCP metadata."""
        return self._pack_result(selection, result)

    def build_stage_summary(
        self,
        *,
        selection: PluginSelectionConfig,
        plugin_kind: str,
        runs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Summarize repeated executions inside one stage."""
        warnings: list[str] = []
        for run in runs:
            warnings.extend(run.get("warnings", []))
        return {
            "plugin_name": selection.name,
            "plugin_kind": plugin_kind,
            "run_count": len(runs),
            "warnings": warnings,
            "runs": runs,
        }

    def _pack_result(
        self,
        selection: PluginSelectionConfig,
        result: PluginExecutionResult,
    ) -> dict[str, Any]:
        packed = result.model_dump(mode="json")
        packed["plugin_name"] = selection.name
        return packed


PluginExecutionManager = PluginManager
