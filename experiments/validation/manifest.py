"""Event manifest generation for real flood validation sets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.data_adapters import FloodEventData, RealEventDataAdapter


@dataclass(frozen=True)
class ManifestSelection:
    minimal_static: set[str]
    dynamic: set[str]
    data_quality_blockers: dict[str, str]
    stress_or_safety_events: set[str]


def build_event_manifest(
    adapter: RealEventDataAdapter,
    *,
    selected_static: list[str] | tuple[str, ...] | None = None,
    selected_dynamic: list[str] | tuple[str, ...] | None = None,
    data_quality_blockers: dict[str, str] | None = None,
    stress_or_safety_events: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Scan flood events and summarize runtime-visible properties."""

    selection = ManifestSelection(
        minimal_static={_normalize_event_id(item) for item in selected_static or []},
        dynamic={_normalize_event_id(item) for item in selected_dynamic or []},
        data_quality_blockers={
            _normalize_event_id(event_id): str(reason)
            for event_id, reason in (data_quality_blockers or {}).items()
        },
        stress_or_safety_events={
            _normalize_event_id(event_id) for event_id in (stress_or_safety_events or [])
        },
    )
    rows = [
        _event_manifest_row(adapter, raw_path.stem, selection)
        for raw_path in adapter.list_raw_flood_event_files()
    ]
    return sorted(rows, key=lambda item: item["event_id"])


def write_manifest_csv(rows: list[dict[str, Any]], path: str | Path) -> Path:
    """Persist manifest rows as CSV."""

    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(resolved, index=False, encoding="utf-8-sig")
    return resolved


def _event_manifest_row(
    adapter: RealEventDataAdapter,
    event_id: str,
    selection: ManifestSelection,
) -> dict[str, Any]:
    event = adapter.load_event(event_id)
    quality = adapter.inspect_quality(event_id)
    levels = [float(record.level) for record in event.records if record.level is not None]
    inflows = [float(record.inflow) for record in event.records if record.inflow is not None]
    if not levels or not inflows:
        raise ValueError(f"{event.event_id}: missing level or inflow for manifest statistics")

    peak_inflow = max(inflows)
    max_level = max(levels)
    blocker_reason = selection.data_quality_blockers.get(event.event_id)
    reason = quality.reason
    if blocker_reason and blocker_reason not in reason:
        reason = "; ".join(part for part in (reason, blocker_reason) if part)
    return {
        "event_id": event.event_id,
        "file_name": Path(quality.raw_path).name if quality.raw_path else event.source_path.name,
        "source_path": event.source_path.as_posix(),
        "raw_path": quality.raw_path,
        "processed_path": quality.processed_path,
        "n_steps": len(event.records),
        "duration_h": event.duration_hours,
        "time_step_hours": event.time_step_hours,
        "peak_inflow": round(peak_inflow, 3),
        "mean_inflow": round(sum(inflows) / len(inflows), 3),
        "max_level": round(max_level, 3),
        "initial_level": round(levels[0], 3),
        "risk_class": _risk_class(adapter.flood_limit_level, max_level, peak_inflow),
        "duration_class": _duration_class(event.duration_hours),
        "selected_for_minimal_static": event.event_id in selection.minimal_static,
        "selected_for_dynamic": event.event_id in selection.dynamic,
        "selected_for_stress_or_safety": event.event_id in selection.stress_or_safety_events,
        "has_forecast": _has_forecast_file(adapter.data_root, event.event_id) or event.has_prediction,
        "event_class": quality.event_class,
        "selection_class": (
            "stress_or_safety"
            if event.event_id in selection.stress_or_safety_events
            else "standard"
        ),
        "raw_row_count": quality.raw_row_count,
        "processed_row_count": quality.processed_row_count,
        "missing_inflow_count": quality.inflow_missing_count_raw,
        "missing_outflow_count": quality.outflow_missing_count_raw,
        "inflow_missing_count_raw": quality.inflow_missing_count_raw,
        "outflow_missing_count_raw": quality.outflow_missing_count_raw,
        "rows_dropped_due_to_missing_inflow": quality.rows_dropped_due_to_missing_inflow,
        "outflow_filled_by_inflow_count": quality.outflow_filled_by_inflow_count,
        "outflow_fallback_applied": quality.outflow_fallback_applied,
        "inflow_drop_applied": quality.inflow_drop_applied,
        "time_axis_invalid": quality.time_axis_invalid,
        "valid_time_axis": quality.valid_time_axis,
        "non_increasing_time_count": quality.non_increasing_time_count,
        "irregular_time_step_count": quality.irregular_time_step_count,
        "expected_time_step_hours": quality.expected_time_step_hours,
        "time_axis_anomalies": "; ".join(quality.time_axis_anomalies),
        "strict_clean_eligible": quality.strict_clean_eligible,
        "repaired_executable_eligible": quality.repaired_executable_eligible,
        "diagnostic_only": quality.diagnostic_only,
        "data_quality_status": quality.data_quality_status,
        "data_quality_reason": reason,
        "notes": quality.notes,
        "excluded_from_clean_static_success_denominator": not quality.strict_clean_eligible,
        "excluded_from_repaired_static_success_denominator": (
            not quality.repaired_executable_eligible
        ),
    }


def _normalize_event_id(value: str) -> str:
    return Path(str(value)).stem.removesuffix("_with_pred")


def _has_forecast_file(data_root: Path, event_id: str) -> bool:
    candidates = [
        data_root / f"{event_id}_with_pred.csv",
        data_root / "withpred" / f"{event_id}.csv",
        data_root / "withpred" / f"{event_id}_with_pred.csv",
    ]
    return any(path.exists() for path in candidates)


def _risk_class(flood_limit_level: float, max_level: float, peak_inflow: float) -> str:
    if max_level >= flood_limit_level or peak_inflow >= 3000.0:
        return "high"
    if max_level >= flood_limit_level - 1.0 or peak_inflow >= 1000.0:
        return "medium"
    return "low"


def _duration_class(duration_hours: int) -> str:
    if duration_hours <= 72:
        return "short"
    if duration_hours <= 168:
        return "medium"
    return "long"
