"""Scenario-set loading and expansion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ScenarioCase:
    """One event/workflow/method validation case."""

    scenario_group: str
    workflow_type: str
    event: str
    method_id: str
    stage_offsets: tuple[int, ...] | None = None
    rolling_event_path: str | None = None
    data_quality_blocker: bool = False
    data_quality_reason: str | None = None
    instructions: dict[int, str] | None = None
    target_adjustments_m: dict[int, float] | None = None


def load_scenario_set(
    name: str,
    *,
    config_dir: str | Path = "experiments/config",
    workflow: str = "all",
    method: str = "all",
) -> tuple[dict[str, Any], list[ScenarioCase]]:
    """Load a scenario-set YAML and expand runnable cases."""

    path = Path(config_dir) / f"{name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Missing scenario-set config: {path}")
    with path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"Scenario-set config must be a mapping: {path}")
    return cfg, _expand_cases(cfg, workflow=workflow, method=method)


def selected_static_events(cfg: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for group_name in ("s0", "s1"):
        group = cfg.get(group_name) or {}
        events.extend(str(item) for item in group.get("static_events", []))
    return _dedupe(events)


def selected_dynamic_events(cfg: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for group_name in ("s0", "s2"):
        group = cfg.get(group_name) or {}
        events.extend(str(item) for item in group.get("dynamic_events", []))
    return _dedupe(events)


def selected_stress_or_safety_events(cfg: dict[str, Any]) -> list[str]:
    items = cfg.get("stress_or_safety_events") or []
    return _dedupe([str(item) for item in items])


def data_quality_blockers(cfg: dict[str, Any], workflow_type: str = "static") -> dict[str, str]:
    """Return event_id -> blocker reason for events excluded from clean denominators."""

    raw = cfg.get("data_quality_blockers") or {}
    if not isinstance(raw, dict):
        return {}
    key = f"{workflow_type}_events"
    value = raw.get(key, {})
    if isinstance(value, list):
        return {str(item): "data_quality_blocker" for item in value}
    if not isinstance(value, dict):
        return {}
    blockers: dict[str, str] = {}
    for event, metadata in value.items():
        event_id = str(event)
        if isinstance(metadata, dict):
            reason = metadata.get("reason") or metadata.get("failure_reason")
        else:
            reason = metadata
        blockers[event_id] = str(reason or "data_quality_blocker")
    return blockers


def resolve_rolling_event_paths(cfg: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for group_name in ("s0", "s3"):
        group = cfg.get(group_name) or {}
        paths.extend(_coerce_rolling_paths(group.get("rolling_event_paths")))
    if not paths:
        paths = _scan_default_forecast_paths(cfg)
    return _dedupe(paths)


def _expand_cases(cfg: dict[str, Any], *, workflow: str, method: str) -> list[ScenarioCase]:
    cases: list[ScenarioCase] = []
    workflow_filter = None if workflow == "all" else workflow
    for group_name in ("s0", "s1", "s2", "s3"):
        group = cfg.get(group_name) or {}
        methods = _resolve_methods(group, method)
        for method_id in methods:
            if workflow_filter in (None, "static"):
                cases.extend(_static_cases(group_name, group, method_id, cfg))
            if workflow_filter in (None, "dynamic"):
                cases.extend(_dynamic_cases(group_name, group, method_id))
            if workflow_filter in (None, "rolling"):
                cases.extend(_rolling_cases(group_name, group, method_id, cfg))
    return cases


def _static_cases(
    group_name: str,
    group: dict[str, Any],
    method_id: str,
    cfg: dict[str, Any],
) -> list[ScenarioCase]:
    blockers = data_quality_blockers(cfg, "static")
    return [
        ScenarioCase(
            scenario_group=group_name,
            workflow_type="static",
            event=str(event),
            method_id=method_id,
            data_quality_blocker=str(event) in blockers,
            data_quality_reason=blockers.get(str(event)),
        )
        for event in group.get("static_events", [])
    ]


def _dynamic_cases(group_name: str, group: dict[str, Any], method_id: str) -> list[ScenarioCase]:
    stage_offsets = tuple(int(item) for item in group.get("dynamic_stage_offsets", []))
    instructions = {
        int(offset): str(text)
        for offset, text in (group.get("dynamic_instructions") or {}).items()
    }
    target_adjustments = {
        int(offset): float(value)
        for offset, value in (group.get("dynamic_target_adjustments_m") or {}).items()
    }
    return [
        ScenarioCase(
            scenario_group=group_name,
            workflow_type="dynamic",
            event=str(event),
            method_id=method_id,
            stage_offsets=stage_offsets or None,
            instructions=instructions or None,
            target_adjustments_m=target_adjustments or None,
        )
        for event in group.get("dynamic_events", [])
    ]


def _rolling_cases(
    group_name: str,
    group: dict[str, Any],
    method_id: str,
    cfg: dict[str, Any],
) -> list[ScenarioCase]:
    paths = _coerce_rolling_paths(group.get("rolling_event_paths"))
    if group_name == "s3" and not paths:
        paths = _scan_default_forecast_paths(cfg)
    return [
        ScenarioCase(
            scenario_group=group_name,
            workflow_type="rolling",
            event=Path(path).stem,
            method_id=method_id,
            rolling_event_path=str(path),
        )
        for path in paths
    ] + _rolling_stress_cases(group_name, group, method_id)


def _rolling_stress_cases(
    group_name: str,
    group: dict[str, Any],
    method_id: str,
) -> list[ScenarioCase]:
    cases: list[ScenarioCase] = []
    for item in group.get("rolling_forecast_error_scenarios", []) or []:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event") or item.get("event_id") or "").strip()
        pattern = str(item.get("pattern") or item.get("scenario") or "").strip()
        if not event or not pattern:
            continue
        cases.append(
            ScenarioCase(
                scenario_group=group_name,
                workflow_type="rolling",
                event=f"{event}_with_pred_{pattern}",
                method_id=method_id,
                rolling_event_path=f"stress://{event}?pattern={pattern}",
            )
        )
    return cases


def _resolve_methods(group: dict[str, Any], requested: str) -> list[str]:
    configured = [str(item) for item in group.get("methods", [])] or ["tools_only"]
    if requested == "all":
        return configured
    if requested not in configured:
        return []
    return [requested]


def _coerce_rolling_paths(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if value == "auto":
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _scan_default_forecast_paths(cfg: dict[str, Any]) -> list[str]:
    data_root = Path((cfg.get("data") or {}).get("root", "data"))
    paths = sorted(data_root.glob("*_with_pred.csv"))
    configured = (cfg.get("data") or {}).get("predicted_event")
    if configured:
        paths.append(Path(configured))
    resolved: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        normalized = path.as_posix()
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return resolved


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
