"""Config loading for paper-validation phases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PaperPhaseConfig:
    name: str
    scenario_groups: tuple[str, ...]
    methods: tuple[str, ...]


def load_paper_validation_config(
    path: str | Path = "experiments/config/paper_validation.yml",
) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Missing paper validation config: {resolved}")
    with resolved.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Paper validation config must be a mapping: {resolved}")
    return payload


def load_phase_config(cfg: dict[str, Any], phase: str) -> PaperPhaseConfig:
    phases = cfg.get("phases") or {}
    if phase not in phases:
        raise ValueError(f"Unknown paper validation phase: {phase}")
    payload = phases[phase] or {}
    return PaperPhaseConfig(
        name=phase,
        scenario_groups=tuple(str(item) for item in payload.get("scenario_groups", [])),
        methods=tuple(str(item) for item in payload.get("methods", [])),
    )
