"""Plugin base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from ..constraints import ConstraintRegistry
from ..metrics import MetricRegistry
from ..rules import RuleRegistry
from .models import (
    BasePluginContext,
    InputPluginContext,
    PluginExecutionResult,
    PluginKind,
    PluginManifest,
    PluginStage,
    PostPluginContext,
    ReportPluginContext,
    StepPluginContext,
)


class PluginBase(ABC):
    """插件基类 (Plugin Base Class)."""

    @abstractmethod
    def initialize(self) -> None:
        """初始化插件."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取插件名称."""
        pass


class ConstraintPluginBase(PluginBase):
    """Base class for constraint plugins."""

    @abstractmethod
    def register_constraints(self, registry: ConstraintRegistry) -> None:
        """Register custom constraints."""


class RulePluginBase(PluginBase):
    """Base class for rule plugins."""

    @abstractmethod
    def register_rules(self, registry: RuleRegistry) -> None:
        """Register custom rules."""


class MetricPluginBase(PluginBase):
    """Base class for metric plugins."""

    @abstractmethod
    def register_metrics(self, registry: MetricRegistry) -> None:
        """Register custom metrics."""


class ExecutionPluginBase(ABC):
    """Unified base class for execution plugins."""

    plugin_name: ClassVar[str]
    plugin_kind: ClassVar[PluginKind]
    stage: ClassVar[PluginStage]
    summary: ClassVar[str]
    applicable_scenarios: ClassVar[list[str]] = []
    required_inputs: ClassVar[list[str]] = []
    optional_inputs: ClassVar[list[str]] = []
    config_schema: ClassVar[dict[str, Any]] = {}
    output_schema: ClassVar[dict[str, Any]] = {}
    limitations: ClassVar[list[str]] = []
    capability_tags: ClassVar[list[str]] = []
    requires: ClassVar[list[str]] = []
    provides: ClassVar[list[str]] = []
    depends_on: ClassVar[list[str]] = []

    def describe(self) -> dict[str, Any]:
        """Return structured plugin metadata."""
        return PluginManifest(
            plugin_name=self.plugin_name,
            plugin_kind=self.plugin_kind,
            plugin_type=self.plugin_kind,
            stage=self.stage,
            summary=self.summary,
            applicable_scenarios=list(self.applicable_scenarios),
            required_inputs=list(self.required_inputs),
            optional_inputs=list(self.optional_inputs),
            config_schema=dict(self.config_schema),
            output_schema=dict(self.output_schema),
            limitations=list(self.limitations),
            capability_tags=list(self.capability_tags),
            requires=list(self.requires),
            provides=list(self.provides),
            depends_on=list(self.depends_on),
        ).model_dump(mode="json")

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize plugin config."""

    @abstractmethod
    def validate_inputs(self, context: BasePluginContext) -> None:
        """Validate the provided execution context."""

    @abstractmethod
    def execute(
        self,
        context: BasePluginContext,
        config: dict[str, Any],
    ) -> PluginExecutionResult:
        """Execute the plugin."""


class InputPluginBase(ExecutionPluginBase):
    """Base class for input-stage plugins."""

    plugin_kind: ClassVar[PluginKind] = "input"
    stage: ClassVar[PluginStage] = PluginStage.INFLOW_GENERATION

    def validate_inputs(self, context: BasePluginContext) -> None:
        if not isinstance(context, InputPluginContext):
            raise TypeError("InputPluginBase requires InputPluginContext")


class StepPluginBase(ExecutionPluginBase):
    """Base class for step-stage plugins."""

    plugin_kind: ClassVar[PluginKind] = "step"
    stage: ClassVar[PluginStage] = PluginStage.DISPATCH_STEP

    def validate_inputs(self, context: BasePluginContext) -> None:
        if not isinstance(context, StepPluginContext):
            raise TypeError("StepPluginBase requires StepPluginContext")


class PostPluginBase(ExecutionPluginBase):
    """Base class for post-simulation plugins."""

    plugin_kind: ClassVar[PluginKind] = "post"
    stage: ClassVar[PluginStage] = PluginStage.POST_SIMULATION

    def validate_inputs(self, context: BasePluginContext) -> None:
        if not isinstance(context, PostPluginContext):
            raise TypeError("PostPluginBase requires PostPluginContext")


class ReportPluginBase(ExecutionPluginBase):
    """Base class for report-generation plugins."""

    plugin_kind: ClassVar[PluginKind] = "report"
    stage: ClassVar[PluginStage] = PluginStage.REPORT_GENERATION

    def validate_inputs(self, context: BasePluginContext) -> None:
        if not isinstance(context, ReportPluginContext):
            raise TypeError("ReportPluginBase requires ReportPluginContext")
