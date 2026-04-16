from __future__ import annotations

from datetime import datetime


DEFAULT_SCENARIO_START_TIME = datetime(2025, 6, 1, 0, 0, 0)


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def resolve_scenario_start_time(scenario: dict) -> datetime:
    for key in (
        "scenario_start_time",
        "start_time",
        "start_timestamp",
        "forecast_start_time",
    ):
        parsed = _parse_datetime(scenario.get(key))
        if parsed is not None:
            return parsed
    return DEFAULT_SCENARIO_START_TIME
