"""Integration tests for execution plugin support through services."""

from __future__ import annotations

from datetime import datetime, timedelta

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import TimeHorizon
from pyresops.plugins import PluginBundleConfig, PluginManager, PluginSelectionConfig
from pyresops.services import ProgramService, SimulationService


def _build_rainfall_only_forecast() -> ForecastBundle:
    timestamps = [datetime(2024, 7, 1) + timedelta(hours=index) for index in range(4)]
    return ForecastBundle(
        forecast_time=timestamps[0],
        series=[
            ForecastSeries(
                variable="rainfall",
                timestamps=timestamps,
                values=[10.0, 20.0, 10.0, 0.0],
                unit="mm/h",
            )
        ],
    )


def test_simulation_service_runs_input_step_and_post_plugins(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    program_service = ProgramService()
    simulation_service = SimulationService(
        sample_reservoir_spec,
        program_service.get_module_registry(),
        plugin_manager=PluginManager(),
    )
    program = program_service.create_program(
        name="plugin_pipeline",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 3, 0, 0),
            time_step=3600,
        ),
        module_configs=[{"module_type": "constant_release", "parameters": {"target_release": 100.0}}],
    )
    plugin_bundle = PluginBundleConfig(
        input=PluginSelectionConfig(
            name="simple_rainfall_runoff",
            config={"runoff_coefficient": 0.5, "lag_steps": 0, "baseflow": 1.0},
        ),
        step=PluginSelectionConfig(
            name="gate_release_calculator",
            config={
                "discharge_coefficient": 0.6,
                "gate_width": 1.0,
                "gate_count": 1,
                "gate_height": 1.0,
                "gate_opening": 0.1,
                "gate_sill_level": 160.0,
            },
        ),
        post=PluginSelectionConfig(
            name="muskingum_routing",
            config={"k": 3.0, "x": 0.2, "dt_hours": 1.0},
        ),
    )

    result = simulation_service.run_simulation(
        program,
        sample_initial_state,
        _build_rainfall_only_forecast(),
        plugin_bundle=plugin_bundle,
    )

    assert "plugin_results" in result.metadata
    assert "input" in result.metadata["plugin_results"]
    assert "step" in result.metadata["plugin_results"]
    assert "post" in result.metadata["plugin_results"]
    assert result.snapshots[0].outflow >= 0.0
