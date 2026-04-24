"""Models for provider-based data materialization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from datetime import datetime

from ..domain.forecast import ForecastBundle
from ..domain.policy import PolicyBundle
from ..domain.program import DispatchProgram
from ..domain.reservoir import ReservoirSpec, ReservoirState
from ..plugins.models import ExecutionConfig


ProviderTarget = Literal[
    "reservoir_bootstrap",
    "forecast_bundle",
    "dispatch_program",
    "scenario_input_bundle",
]


class DataRequest(BaseModel):
    """Describes a typed materialization request."""

    target_type: ProviderTarget
    source_hint: str | None = None
    locator: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    inline_data: dict[str, Any] | None = None


class DataResolutionResult(BaseModel):
    """Structured result returned by provider resolution."""

    target_type: ProviderTarget
    provider_name: str
    source_hint: str | None = None
    locator: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReservoirYamlError(ValueError):
    """Raised when reservoir YAML is missing required fields or malformed."""


class InitialSnapshotConfig(BaseModel):
    """Optional initial snapshot fields loaded from YAML."""

    level: float | None = Field(default=None)
    inflow: float = Field(default=0.0)
    outflow: float | None = Field(default=None)
    timestamp: datetime | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class ReservoirBootstrap:
    """Validated reservoir bootstrap payload."""

    spec: "ReservoirSpec"
    snapshot: InitialSnapshotConfig | None = None
    execution: ExecutionConfig | None = None

    def create_initial_state(self) -> ReservoirState:
        """Create initial `ReservoirState` from bootstrap snapshot config."""
        template = self.snapshot or InitialSnapshotConfig()
        level = float(template.level if template.level is not None else self.spec.normal_level)
        inflow = float(template.inflow)
        outflow = float(template.outflow if template.outflow is not None else inflow)
        timestamp = template.timestamp or datetime.now()
        storage = self.spec.level_storage_curve.get_storage(level)
        metadata = {
            **template.metadata,
            "reservoir_id": self.spec.id,
            "source": "yaml_bootstrap",
        }
        return ReservoirState(
            timestamp=timestamp,
            level=level,
            storage=storage,
            inflow=inflow,
            outflow=outflow,
            metadata=metadata,
        )


@dataclass(slots=True)
class ScenarioInputBundle:
    """Convenience bundle for one executable scenario input set."""

    bootstrap: ReservoirBootstrap
    initial_state: ReservoirState
    forecast: ForecastBundle
    program: DispatchProgram
    policy_bundle: PolicyBundle | None = None
    plugin_bundle: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @property
    def source_path(self) -> Path | None:
        """Return the scenario manifest source path when present."""
        path = (self.metadata or {}).get("source_path")
        return None if path is None else Path(path)
