"""Preview the built-in rainfall-runoff input plugin."""

from __future__ import annotations

from pprint import pprint

from pyresops.plugins import PluginBundleConfig, PluginManager, PluginSelectionConfig

from _plugin_demo_support import build_demo_state, build_rainfall_forecast


def main() -> None:
    manager = PluginManager()
    forecast = build_rainfall_forecast()
    state = build_demo_state(timestamp=forecast.forecast_time)
    bundle = PluginBundleConfig(
        input=PluginSelectionConfig(
            name="simple_rainfall_runoff",
            config={"runoff_coefficient": 0.6, "lag_steps": 1, "baseflow": 5.0},
        )
    )

    resolved_forecast, plugin_results, _ = manager.prepare_forecast(
        forecast=forecast,
        initial_state=state,
        plugin_bundle=bundle,
    )
    inflow_series = resolved_forecast.get_series("inflow")
    pprint(plugin_results)
    pprint(inflow_series.model_dump(mode="json") if inflow_series else None)


if __name__ == "__main__":
    main()
