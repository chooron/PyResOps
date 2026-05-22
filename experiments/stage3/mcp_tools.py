"""Stage 3 MCP scenario builder: constructs scenario payloads from Stage 1/2 event definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.data_adapters.real_events import RealEventDataAdapter
from experiments.stage1.constraints import get_flood_limit, get_season_name


def build_stage3_scenario(
    event_id: str,
    workflow_type: str,
    adapter: RealEventDataAdapter,
    *,
    workflow_stage: str | None = None,
    offset_hours: int = 0,
    use_predict: bool = False,
    operator_instruction: str = "",
    replan_reason: str = "initial",
    stage_offset_hours: int | None = None,
) -> dict[str, Any]:
    """Build a scenario payload dict compatible with MCP tool inputs and TrueMcpSkillRunner.

    Uses adapter.to_payload() to produce the exact field names the MCP tools expect:
    start_time, current_level, initial_storage, initial_inflow, time_step_hours,
    benchmark_inflow_series_m3s, etc.
    """
    actual_offset = stage_offset_hours if stage_offset_hours is not None else offset_hours

    if use_predict or workflow_type in ("rolling", "rolling_replan", "rolling_retain"):
        withpred_path = adapter.data_root / "withpred" / f"{event_id}.csv"
        event = adapter.load_predicted_event(withpred_path)
    else:
        event = adapter.load_event(event_id)

    stage_id = workflow_stage or (
        "static" if workflow_type == "static"
        else f"rolling_{actual_offset}h" if workflow_type in ("rolling", "rolling_replan", "rolling_retain")
        else f"T0"
    )
    scenario_id = f"{event_id}_{stage_id}"

    # Determine flood limit for target_level
    sliced = event.slice_from_hour(actual_offset) if actual_offset > 0 else event
    first_idx = sliced.first_valid_index()
    first = sliced.records[first_idx]
    flood_limit = get_flood_limit(first.time.month, first.time.day)

    # Use adapter.to_payload() to get the exact field names the MCP tools expect
    payload = adapter.to_payload(
        event,
        workflow_type=workflow_type,
        scenario_id=scenario_id,
        stage_offset_hours=actual_offset,
        operator_instruction=operator_instruction,
        target_level=flood_limit,
        target_level_tolerance=0.5,
    )

    # Add Stage 3 specific fields
    payload["stage_id"] = stage_id
    payload["replan_reason"] = replan_reason
    payload["season"] = get_season_name(first.time.month, first.time.day)
    payload["flood_limit_level"] = flood_limit

    return payload


def list_static_events(adapter: RealEventDataAdapter) -> list[str]:
    return [p.stem for p in adapter.list_raw_flood_event_files()]


def list_dynamic_events(config: dict[str, Any]) -> list[str]:
    return [str(e) for e in config.get("dynamic_events", [])]


def list_rolling_events(config: dict[str, Any]) -> list[str]:
    return [str(e) for e in config.get("rolling_events", [])]
