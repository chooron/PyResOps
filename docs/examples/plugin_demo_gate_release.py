"""Preview the built-in gate release step plugin."""

from __future__ import annotations

from pprint import pprint

from pyresops.plugins import PluginManager, PluginSelectionConfig, StepPluginContext

from _plugin_demo_support import build_demo_state


def main() -> None:
    manager = PluginManager()
    state = build_demo_state()
    selection = PluginSelectionConfig(
        name="gate_release_calculator",
        config={
            "discharge_coefficient": 0.7,
            "gate_width": 8.0,
            "gate_count": 2,
            "gate_height": 1.0,
            "gate_opening": 0.4,
            "gate_sill_level": 160.0,
        },
    )
    result = manager.execute_step(
        selection=selection,
        context=StepPluginContext(
            step_index=0,
            state=state,
            inflow=6000.0,
            baseline_outflow=5500.0,
            active_module="constant_release",
        ),
    )
    if result is not None:
        pprint(manager.pack_selection_result(selection=selection, result=result))


if __name__ == "__main__":
    main()
