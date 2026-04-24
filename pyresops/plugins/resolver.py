"""Capability resolution for execution plugins."""

from __future__ import annotations

from ..domain.forecast import ForecastBundle
from .models import PluginBundleConfig
from .registry import ExecutionPluginRegistry
from .models import PluginResolutionResult


class PluginResolver:
    """Resolve which plugins are applicable for a task."""

    def __init__(self, registry: ExecutionPluginRegistry):
        self.registry = registry

    def resolve_for_task(
        self,
        *,
        forecast: ForecastBundle | None = None,
        plugin_bundle: PluginBundleConfig | None = None,
        requested_capabilities: list[str] | None = None,
    ) -> PluginResolutionResult:
        """Resolve a plugin bundle recommendation."""
        requested_capabilities = requested_capabilities or []
        if plugin_bundle and not plugin_bundle.is_empty():
            selected: dict[str, str] = {}
            for kind, selection in plugin_bundle.iter_selections():
                selected[kind] = selection.name
            return PluginResolutionResult(
                status="executable",
                selected=selected,
                rationale=["Using explicitly selected plugin bundle."],
            )

        if forecast is not None and forecast.get_series("inflow") is None:
            rainfall = forecast.get_series("rainfall")
            if rainfall is not None:
                input_candidates = [
                    item["plugin_name"] for item in self.registry.list("input")
                ]
                if len(input_candidates) == 1:
                    return PluginResolutionResult(
                        status="executable",
                        selected={"input": input_candidates[0]},
                        rationale=[
                            "No inflow series present.",
                            "Rainfall series detected.",
                            f"Auto-selected unique input plugin '{input_candidates[0]}'.",
                        ],
                    )
                if len(input_candidates) > 1:
                    return PluginResolutionResult(
                        status="ambiguous",
                        ambiguous={"input": input_candidates},
                        rationale=[
                            "Rainfall-only input detected but multiple input plugins are available.",
                        ],
                    )
                return PluginResolutionResult(
                    status="unavailable",
                    missing=["input"],
                    rationale=[
                        "Rainfall-only input detected but no input plugin is loaded.",
                    ],
                )

        if any(tag in requested_capabilities for tag in ["downstream_impact", "routing"]):
            post_candidates = [item["plugin_name"] for item in self.registry.list("post")]
            if not post_candidates:
                return PluginResolutionResult(
                    status="unavailable",
                    missing=["post"],
                    rationale=["Downstream impact capability requested but no post plugin is loaded."],
                )

        return PluginResolutionResult(
            status="unavailable",
            missing=[],
            rationale=["No plugin selection was required or no safe automatic selection rule matched."],
        )
