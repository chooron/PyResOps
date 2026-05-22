"""Run a full input + step + post plugin pipeline through `SimulationService`."""

from __future__ import annotations

from pprint import pprint

from pyresops.domain.program import TimeHorizon
from pyresops.plugins import PluginBundleConfig, PluginManager, PluginSelectionConfig
from pyresops.services import ProgramService, SimulationService

from _plugin_demo_support import build_demo_spec, build_demo_state, build_rainfall_forecast


def main() -> None:
    spec = build_demo_spec()
    state = build_demo_state()
    forecast = build_rainfall_forecast()

    program_service = ProgramService()
    simulation_service = SimulationService(
        spec,
        program_service.get_module_registry(),
        plugin_manager=PluginManager(),
    )
    program = program_service.create_program(
        name="plugin_pipeline_demo",
        time_horizon=TimeHorizon(
            start=forecast.forecast_time,
            end=forecast.series[0].timestamps[-1],
            time_step=3600,
        ),
        module_configs=[{"module_type": "constant_release", "parameters": {"target_release": 500.0}}],
    )
    bundle = PluginBundleConfig(
        input=PluginSelectionConfig(
            name="simple_rainfall_runoff",
            config={"runoff_coefficient": 0.6, "lag_steps": 0, "baseflow": 10.0},
        ),
        step=PluginSelectionConfig(
            name="gate_release_calculator",
            config={
                "discharge_coefficient": 0.7,
                "gate_width": 6.0,
                "gate_count": 2,
                "gate_height": 1.0,
                "gate_opening": 0.25,
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
        state,
        forecast,
        plugin_bundle=bundle,
    )
    pprint(result.metadata.get("plugin_results", {}))
    pprint(result.snapshots[0].model_dump(mode="json"))


if __name__ == "__main__":
    main()
