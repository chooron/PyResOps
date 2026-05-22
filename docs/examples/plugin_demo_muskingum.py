"""Preview the built-in Muskingum post plugin."""

from __future__ import annotations

from pprint import pprint

from pyresops.plugins import PluginManager, PluginSelectionConfig, PostPluginContext
from pyresops.tools.common import build_simulation_result_from_outflow_payload

from _plugin_demo_support import build_demo_state


def main() -> None:
    manager = PluginManager()
    state = build_demo_state()
    outflow_data = {
        "timestamps": [
            "2024-07-01T00:00:00",
            "2024-07-01T01:00:00",
            "2024-07-01T02:00:00",
            "2024-07-01T03:00:00",
        ],
        "values": [5000.0, 6500.0, 6200.0, 4800.0],
    }
    simulation_result = build_simulation_result_from_outflow_payload(
        program_id="post_demo",
        outflow_data=outflow_data,
        reference_state=state,
    )
    selection = PluginSelectionConfig(
        name="muskingum_routing",
        config={"k": 3.0, "x": 0.2, "dt_hours": 1.0},
    )
    result = manager.execute_post(
        selection=selection,
        context=PostPluginContext(simulation_result=simulation_result),
    )
    if result is not None:
        pprint(manager.pack_selection_result(selection=selection, result=result))


if __name__ == "__main__":
    main()
