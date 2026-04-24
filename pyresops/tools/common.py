"""Shared MCP tool helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..domain.forecast import ForecastBundle, ForecastSeries
from ..domain.result import SimulationResult, StateSnapshot
from ..domain.reservoir import ReservoirState
from ..plugins import PluginBundleConfig


def build_forecast_bundle_from_payload(forecast_data: dict[str, Any]) -> ForecastBundle:
    """Build a `ForecastBundle` from MCP payload data."""
    raw_forecast_time = forecast_data.get("forecast_time")
    forecast_time = (
        datetime.fromisoformat(raw_forecast_time)
        if isinstance(raw_forecast_time, str)
        else datetime.now()
    )

    if isinstance(forecast_data.get("series"), list):
        series_items = [_build_series(item) for item in forecast_data["series"]]
    else:
        timestamps = forecast_data.get("timestamps")
        if not isinstance(timestamps, list) or not timestamps:
            raise ValueError("forecast_data must contain timestamps or series")
        parsed_timestamps = [datetime.fromisoformat(item) for item in timestamps]
        series_items: list[ForecastSeries] = []
        if forecast_data.get("inflow_values") is not None:
            inflow_values = [float(value) for value in forecast_data["inflow_values"]]
            if len(parsed_timestamps) != len(inflow_values):
                raise ValueError("forecast_data timestamps and inflow_values length mismatch")
            series_items.append(
                ForecastSeries(
                    variable="inflow",
                    timestamps=parsed_timestamps,
                    values=inflow_values,
                    unit=str(forecast_data.get("inflow_unit", "m3/s")),
                )
            )
        if forecast_data.get("rainfall_values") is not None:
            rainfall_values = [float(value) for value in forecast_data["rainfall_values"]]
            if len(parsed_timestamps) != len(rainfall_values):
                raise ValueError("forecast_data timestamps and rainfall_values length mismatch")
            series_items.append(
                ForecastSeries(
                    variable="rainfall",
                    timestamps=parsed_timestamps,
                    values=rainfall_values,
                    unit=str(forecast_data.get("rainfall_unit", "mm/h")),
                )
            )
    if not series_items:
        raise ValueError("forecast_data did not contain any supported forecast series")
    return ForecastBundle(
        forecast_time=forecast_time,
        series=series_items,
        metadata=dict(forecast_data.get("metadata", {})),
    )


def coerce_plugin_bundle(payload: dict[str, Any] | None) -> PluginBundleConfig | None:
    """Parse optional plugin bundle payload."""
    if not payload:
        return None
    bundle = PluginBundleConfig(**payload)
    return None if bundle.is_empty() else bundle


def build_simulation_result_from_outflow_payload(
    *,
    program_id: str,
    outflow_data: dict[str, Any],
    reference_state: ReservoirState | None,
) -> SimulationResult:
    """Build a lightweight `SimulationResult` for post-plugin previews."""
    timestamps = [datetime.fromisoformat(item) for item in outflow_data["timestamps"]]
    values = [float(item) for item in outflow_data["values"]]
    if len(timestamps) != len(values):
        raise ValueError("outflow_data timestamps and values length mismatch")
    if not timestamps:
        raise ValueError("outflow_data must not be empty")

    level = float(reference_state.level) if reference_state else 0.0
    storage = float(reference_state.storage) if reference_state else 0.0
    snapshots = [
        StateSnapshot(
            timestamp=timestamp,
            level=level,
            storage=storage,
            inflow=value,
            outflow=value,
            metadata={},
        )
        for timestamp, value in zip(timestamps, values)
    ]
    return SimulationResult(
        program_id=program_id,
        start_time=timestamps[0],
        end_time=timestamps[-1],
        snapshots=snapshots,
        max_level=level,
        min_level=level,
        avg_outflow=sum(values) / len(values),
        metadata={},
    )


def _build_series(payload: dict[str, Any]) -> ForecastSeries:
    variable = str(payload["variable"])
    timestamps = [datetime.fromisoformat(item) for item in payload["timestamps"]]
    values = [float(item) for item in payload["values"]]
    if len(timestamps) != len(values):
        raise ValueError(f"{variable} timestamps and values length mismatch")
    return ForecastSeries(
        variable=variable,
        timestamps=timestamps,
        values=values,
        unit=str(payload.get("unit", "")),
    )
