"""Shared models for execution plugins."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..domain.forecast import ForecastBundle
from ..domain.reservoir import ReservoirState
from ..domain.result import EvaluationResult, SimulationResult


PluginKind = Literal["input", "step", "post", "report"]
PluginAvailability = Literal["executable", "ambiguous", "unavailable"]


class PluginStage(StrEnum):
    """Explicit execution stages for plugins."""

    PRE_FORECAST = "pre_forecast"
    INFLOW_GENERATION = "inflow_generation"
    PRE_DISPATCH = "pre_dispatch"
    DISPATCH_STEP = "dispatch_step"
    DOWNSTREAM_STEP = "downstream_step"
    POST_SIMULATION = "post_simulation"
    POST_EVALUATION = "post_evaluation"
    REPORT_GENERATION = "report_generation"


class PluginManifest(BaseModel):
    """Structured plugin metadata for discovery and scheduling."""

    plugin_name: str
    plugin_kind: PluginKind
    plugin_type: str | None = None
    stage: PluginStage
    summary: str
    applicable_scenarios: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    capability_tags: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class PluginExecutionResult(BaseModel):
    """Structured execution result returned by all execution plugins."""

    payload: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    used_config: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BasePluginContext(BaseModel):
    """Base context shared across execution plugin phases."""

    metadata: dict[str, Any] = Field(default_factory=dict)


class InputPluginContext(BasePluginContext):
    """Context for input-stage plugins."""

    forecast: ForecastBundle
    initial_state: ReservoirState | None = None
    requested_capabilities: list[str] = Field(default_factory=list)
    execution_options: dict[str, Any] = Field(default_factory=dict)


class StepPluginContext(BasePluginContext):
    """Context for step-stage plugins."""

    step_index: int
    state: ReservoirState
    inflow: float
    baseline_outflow: float
    active_module: str | None = None
    policy_bundle: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)


class PostPluginContext(BasePluginContext):
    """Context for post-simulation plugins."""

    simulation_result: SimulationResult
    evaluation_result: EvaluationResult | None = None
    policy_bundle: dict[str, Any] = Field(default_factory=dict)
    upstream_plugin_results: dict[str, Any] = Field(default_factory=dict)


class ReportPluginContext(BasePluginContext):
    """Context for report-generation plugins."""

    simulation_result: SimulationResult | None = None
    evaluation_result: EvaluationResult | None = None
    plugin_results: dict[str, Any] = Field(default_factory=dict)
    target_audience: str = "default"
    report_options: dict[str, Any] = Field(default_factory=dict)


class PluginSelectionSummary(BaseModel):
    """One selected plugin summary."""

    plugin_kind: PluginKind
    plugin_name: str
    reason: str = ""


class PluginResolutionResult(BaseModel):
    """Capability resolution result for automatic plugin selection."""

    status: PluginAvailability
    selected: dict[str, str] = Field(default_factory=dict)
    ambiguous: dict[str, list[str]] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class PluginSelectionConfig(BaseModel):
    """Configuration for one selected execution plugin."""

    name: str = Field(description="Registered plugin name")
    config: dict[str, Any] = Field(default_factory=dict, description="Plugin-specific config")


class PluginBundleConfig(BaseModel):
    """Optional execution plugins applied around the dispatch chain."""

    input: PluginSelectionConfig | None = None
    step: PluginSelectionConfig | None = None
    post: PluginSelectionConfig | None = None
    report: PluginSelectionConfig | None = None

    def without_input(self) -> "PluginBundleConfig | None":
        """Return a copy without the input plugin selection."""
        if self.input is None:
            return self
        copied = self.model_copy(deep=True)
        copied.input = None
        return None if copied.is_empty() else copied

    def is_empty(self) -> bool:
        """Return whether no plugin is configured."""
        return (
            self.input is None
            and self.step is None
            and self.post is None
            and self.report is None
        )

    def iter_selections(self) -> list[tuple[str, PluginSelectionConfig]]:
        """Return the configured selections as `(kind, selection)` tuples."""
        items: list[tuple[str, PluginSelectionConfig]] = []
        if self.input is not None:
            items.append(("input", self.input))
        if self.step is not None:
            items.append(("step", self.step))
        if self.post is not None:
            items.append(("post", self.post))
        if self.report is not None:
            items.append(("report", self.report))
        return items


class ExecutionConfig(BaseModel):
    """Execution defaults loaded from typed configuration."""

    plugins: PluginBundleConfig | None = None
