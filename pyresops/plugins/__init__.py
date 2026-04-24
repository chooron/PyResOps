"""Plugin system (reserved for future extensions)."""

from .base import (
    ConstraintPluginBase,
    ExecutionPluginBase,
    InputPluginBase,
    MetricPluginBase,
    PluginBase,
    PostPluginBase,
    ReportPluginBase,
    RulePluginBase,
    StepPluginBase,
)
from .builtin import (
    GateReleaseCalculatorPlugin,
    MuskingumRoutingPlugin,
    SimpleRainfallRunoffPlugin,
    register_builtin_plugins,
)
from .loader import PluginLoader
from .manager import PluginExecutionManager, PluginManager
from .models import (
    BasePluginContext,
    ExecutionConfig,
    InputPluginContext,
    PluginBundleConfig,
    PluginExecutionResult,
    PluginManifest,
    PluginResolutionResult,
    PluginSelectionConfig,
    PluginStage,
    PostPluginContext,
    ReportPluginContext,
    StepPluginContext,
)
from .orchestrator import PluginOrchestrator
from .registry import ExecutionPluginRegistry, PluginRegistry
from .resolver import PluginResolver

__all__ = [
    "PluginBase",
    "ConstraintPluginBase",
    "RulePluginBase",
    "MetricPluginBase",
    "PluginRegistry",
    "ExecutionPluginBase",
    "InputPluginBase",
    "StepPluginBase",
    "PostPluginBase",
    "ReportPluginBase",
    "ExecutionPluginRegistry",
    "PluginLoader",
    "PluginResolver",
    "PluginOrchestrator",
    "PluginManager",
    "PluginExecutionManager",
    "ExecutionConfig",
    "PluginSelectionConfig",
    "PluginBundleConfig",
    "PluginExecutionResult",
    "PluginManifest",
    "PluginResolutionResult",
    "PluginStage",
    "BasePluginContext",
    "InputPluginContext",
    "StepPluginContext",
    "PostPluginContext",
    "ReportPluginContext",
    "SimpleRainfallRunoffPlugin",
    "GateReleaseCalculatorPlugin",
    "MuskingumRoutingPlugin",
    "register_builtin_plugins",
]
