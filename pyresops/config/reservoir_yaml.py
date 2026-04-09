"""YAML loaders for reservoir bootstrap information.

This module intentionally focuses on schema normalization and validation. It
accepts either a flat `ReservoirSpec` mapping or a structured mapping with
grouped fields, then returns a strongly-typed bootstrap object consumed by
services.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..domain.reservoir import ReservoirSpec, ReservoirState


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
    """Validated reservoir bootstrap payload.

    Attributes:
        spec: Reservoir static specification.
        snapshot: Optional initial state template.
    """

    spec: ReservoirSpec
    snapshot: InitialSnapshotConfig | None = None

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


def load_reservoir_bootstrap_from_yaml(file_path: str | Path) -> ReservoirBootstrap:
    """Load reservoir bootstrap from YAML file path.

    Supports both:
    - Flat payload compatible with `ReservoirSpec`
    - Structured payload under `reservoir`, with grouped sections:
      `characteristic_levels`, `capacities`, and `curves`
    """
    path = Path(file_path)
    if not path.exists():
        raise ReservoirYamlError(f"Reservoir YAML not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise ReservoirYamlError("Reservoir YAML root must be a mapping")

    raw_spec = payload.get("reservoir", payload)
    if not isinstance(raw_spec, dict):
        raise ReservoirYamlError("`reservoir` section must be a mapping")

    spec_payload = _normalize_spec_payload(raw_spec)
    try:
        spec = ReservoirSpec(**spec_payload)
    except Exception as exc:  # pragma: no cover - delegated validation details
        raise ReservoirYamlError(f"Invalid reservoir spec payload: {exc}") from exc

    raw_snapshot = payload.get("snapshot") or payload.get("initial_snapshot")
    snapshot = InitialSnapshotConfig(**raw_snapshot) if isinstance(raw_snapshot, dict) else None
    return ReservoirBootstrap(spec=spec, snapshot=snapshot)


def _normalize_spec_payload(raw_spec: dict[str, Any]) -> dict[str, Any]:
    """Normalize structured spec payload into `ReservoirSpec` fields."""
    normalized = dict(raw_spec)

    levels = normalized.pop("characteristic_levels", None)
    if isinstance(levels, dict):
        normalized.update(levels)

    capacities = normalized.pop("capacities", None)
    if isinstance(capacities, dict):
        normalized.update(capacities)

    curves = normalized.pop("curves", None)
    if isinstance(curves, dict):
        if "level_storage_curve" not in normalized:
            curve_payload = curves.get("level_storage") or curves.get("level_storage_curve")
            if curve_payload is not None:
                normalized["level_storage_curve"] = curve_payload

        if "discharge_capacity" not in normalized:
            discharge_payload = curves.get("discharge_capacity") or curves.get("discharge")
            if discharge_payload is not None:
                normalized["discharge_capacity"] = discharge_payload

    return normalized
