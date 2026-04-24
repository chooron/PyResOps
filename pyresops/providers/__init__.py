"""Provider-based data materialization APIs."""

from .base import ProviderPluginBase
from .builtin import load_reservoir_bootstrap_from_yaml, register_builtin_providers
from .models import (
    DataRequest,
    DataResolutionResult,
    InitialSnapshotConfig,
    ReservoirBootstrap,
    ReservoirYamlError,
    ScenarioInputBundle,
)
from .registry import ProviderManager, ProviderRegistry

__all__ = [
    "ProviderPluginBase",
    "ProviderRegistry",
    "ProviderManager",
    "DataRequest",
    "DataResolutionResult",
    "InitialSnapshotConfig",
    "ReservoirBootstrap",
    "ReservoirYamlError",
    "ScenarioInputBundle",
    "load_reservoir_bootstrap_from_yaml",
    "register_builtin_providers",
]
