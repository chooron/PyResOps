"""Execution plugin discovery and preview tools."""

from __future__ import annotations

from typing import Any

from ..plugins import (
    PluginBundleConfig,
    PluginManager,
    PluginSelectionConfig,
    PostPluginContext,
    StepPluginContext,
)
from ..services import SnapshotService
from .common import build_forecast_bundle_from_payload, build_simulation_result_from_outflow_payload


def setup_plugin_tools(
    mcp_server: Any,
    plugin_manager: PluginManager,
    snapshot_service: SnapshotService,
) -> None:
    """Setup MCP tools for plugin discovery and preview."""

    @mcp_server.tool()
    def list_plugins(plugin_kind: str | None = None) -> dict[str, Any]:
        """List registered execution plugins and their descriptors."""
        descriptors = plugin_manager.describe_all()
        if plugin_kind:
            descriptors = [item for item in descriptors if item["plugin_kind"] == plugin_kind]
        return {
            "plugins": descriptors,
            "count": len(descriptors),
        }

    @mcp_server.tool()
    def describe_plugin(
        plugin_kind: str,
        plugin_name: str,
    ) -> dict[str, Any]:
        """Describe one registered plugin."""
        try:
            return plugin_manager.describe_plugin(
                plugin_kind=plugin_kind,
                plugin_name=plugin_name,
            )
        except Exception as exc:
            return {"error": str(exc)}

    @mcp_server.tool()
    def resolve_plugins_for_task(
        forecast_data: dict[str, Any] | None = None,
        plugin_bundle: dict[str, Any] | None = None,
        requested_capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """Resolve a safe plugin recommendation for the given task."""
        forecast = (
            build_forecast_bundle_from_payload(forecast_data)
            if isinstance(forecast_data, dict)
            else None
        )
        result = plugin_manager.resolve_plugins_for_task(
            forecast=forecast,
            plugin_bundle=PluginBundleConfig(**plugin_bundle) if plugin_bundle else None,
            requested_capabilities=requested_capabilities,
        )
        return result.model_dump(mode="json")

    @mcp_server.tool()
    def preview_plugin(
        plugin_kind: str,
        plugin_name: str,
        plugin_config: dict[str, Any] | None = None,
        reservoir_id: str | None = None,
        forecast_data: dict[str, Any] | None = None,
        outflow_data: dict[str, Any] | None = None,
        inflow: float | None = None,
        baseline_outflow: float | None = None,
        active_module: str | None = None,
    ) -> dict[str, Any]:
        """Preview one plugin with the appropriate context payload."""
        try:
            selection = PluginSelectionConfig(name=plugin_name, config=plugin_config or {})
            if plugin_kind == "input":
                if not reservoir_id:
                    return {"error": "reservoir_id is required for input plugin preview"}
                state = snapshot_service.get_snapshot(reservoir_id)
                if not state:
                    return {"error": f"Snapshot not found for reservoir: {reservoir_id}"}
                if not isinstance(forecast_data, dict):
                    return {"error": "forecast_data is required for input plugin preview"}
                forecast = build_forecast_bundle_from_payload(forecast_data)
                generated_forecast, plugin_results, _ = plugin_manager.prepare_forecast(
                    forecast=forecast,
                    initial_state=state,
                    plugin_bundle=PluginBundleConfig(input=selection),
                )
                inflow_series = generated_forecast.get_series("inflow")
                return {
                    "reservoir_id": reservoir_id,
                    "plugin_results": plugin_results,
                    "generated_inflow": None if inflow_series is None else inflow_series.model_dump(mode="json"),
                }

            if plugin_kind == "step":
                if not reservoir_id:
                    return {"error": "reservoir_id is required for step plugin preview"}
                state = snapshot_service.get_snapshot(reservoir_id)
                if not state:
                    return {"error": f"Snapshot not found for reservoir: {reservoir_id}"}
                result = plugin_manager.execute_step(
                    selection=selection,
                    context=StepPluginContext(
                        step_index=0,
                        state=state,
                        inflow=float(inflow if inflow is not None else state.inflow),
                        baseline_outflow=float(
                            baseline_outflow if baseline_outflow is not None else state.outflow
                        ),
                        active_module=active_module,
                    ),
                )
                return {
                    "reservoir_id": reservoir_id,
                    "result": None
                    if result is None
                    else plugin_manager.pack_selection_result(selection=selection, result=result),
                }

            if plugin_kind == "post":
                state = snapshot_service.get_snapshot(reservoir_id) if reservoir_id else None
                if not isinstance(outflow_data, dict):
                    return {"error": "outflow_data is required for post plugin preview"}
                simulation_result = build_simulation_result_from_outflow_payload(
                    program_id=f"preview_{plugin_name}",
                    outflow_data=outflow_data,
                    reference_state=state,
                )
                result = plugin_manager.execute_post(
                    selection=selection,
                    context=PostPluginContext(simulation_result=simulation_result),
                )
                return {
                    "reservoir_id": reservoir_id,
                    "result": None
                    if result is None
                    else plugin_manager.pack_selection_result(selection=selection, result=result),
                }

            return {"error": f"Unsupported plugin_kind: {plugin_kind}"}
        except Exception as exc:
            return {"error": str(exc)}
