"""Tests for built-in execution plugins."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.result import SimulationResult, StateSnapshot
from pyresops.plugins.builtin import (
    GateReleaseCalculatorPlugin,
    MuskingumRoutingPlugin,
    SimpleRainfallRunoffPlugin,
)


def _build_rainfall_forecast() -> ForecastBundle:
    timestamps = [datetime(2024, 7, 1) + timedelta(hours=index) for index in range(4)]
    return ForecastBundle(
        forecast_time=timestamps[0],
        series=[
            ForecastSeries(
                variable="rainfall",
                timestamps=timestamps,
                values=[10.0, 20.0, 5.0, 0.0],
                unit="mm/h",
            )
        ],
    )


def _build_simulation_result() -> SimulationResult:
    timestamps = [datetime(2024, 7, 1) + timedelta(hours=index) for index in range(4)]
    snapshots = [
        StateSnapshot(
            timestamp=timestamp,
            level=165.0,
            storage=30.0,
            inflow=100.0 + index * 10.0,
            outflow=80.0 + index * 5.0,
            metadata={},
        )
        for index, timestamp in enumerate(timestamps)
    ]
    return SimulationResult(
        program_id="sim_1",
        start_time=timestamps[0],
        end_time=timestamps[-1],
        snapshots=snapshots,
        max_level=165.0,
        min_level=165.0,
        avg_outflow=sum(snapshot.outflow for snapshot in snapshots) / len(snapshots),
        metadata={},
    )


def test_simple_rainfall_runoff_generates_inflow(sample_initial_state) -> None:
    plugin = SimpleRainfallRunoffPlugin()
    result = plugin.generate(
        forecast=_build_rainfall_forecast(),
        initial_state=sample_initial_state,
        config={"runoff_coefficient": 0.5, "lag_steps": 1},
    )

    generated = result.payload["generated_series"]
    assert generated["variable"] == "inflow"
    assert generated["values"] == [0.0, 5.0, 10.0, 2.5]
    assert "baseflow not provided" in result.warnings[0]


def test_gate_release_calculator_clips_gate_opening(sample_initial_state) -> None:
    plugin = GateReleaseCalculatorPlugin()
    result = plugin.compute(
        state=sample_initial_state,
        inflow=100.0,
        baseline_outflow=100.0,
        active_module="constant_release",
        config={
            "discharge_coefficient": 0.6,
            "gate_width": 8.0,
            "gate_count": 2,
            "gate_height": 1.0,
            "gate_opening": 1.5,
            "gate_sill_level": 160.0,
        },
        step_index=0,
    )

    assert result.payload["estimated_outflow"] > 0.0
    assert result.payload["opening_fraction"] == 1.0
    assert any("clipped" in item for item in result.warnings)


def test_muskingum_routing_returns_peak_summary() -> None:
    plugin = MuskingumRoutingPlugin()
    result = plugin.route(
        simulation_result=_build_simulation_result(),
        config={"k": 3.0, "x": 0.2, "dt_hours": 1.0},
    )

    assert result.payload["peak_flow"] > 0.0
    assert result.payload["downstream_flow_series"]["variable"] == "downstream_flow"
    assert "attenuation_summary" in result.payload


@pytest.mark.parametrize(
    ("plugin", "config"),
    [
        (SimpleRainfallRunoffPlugin(), {"runoff_coefficient": 1.5, "lag_steps": 0}),
        (GateReleaseCalculatorPlugin(), {"discharge_coefficient": 0.0, "gate_width": 1.0, "gate_opening": 0.5}),
        (MuskingumRoutingPlugin(), {"k": 0.0, "x": 0.2, "dt_hours": 1.0}),
    ],
)
def test_builtin_plugin_config_validation_errors(plugin, config) -> None:
    with pytest.raises(ValueError):
        plugin.validate_config(config)
