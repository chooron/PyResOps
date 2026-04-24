"""Integration tests for plugin-aware MCP tools."""

from __future__ import annotations

from datetime import datetime, timedelta

from pyresops.plugins import PluginManager
from pyresops.services import (
    EvaluationService,
    OptimizationService,
    ProgramService,
    RollingOpsService,
    SimulationService,
    SnapshotService,
)
from pyresops.storage import Repository
from pyresops.tools import (
    setup_plugin_tools,
    setup_rolling_ops_tools,
    setup_simulation_tools,
)


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _rainfall_payload() -> dict[str, object]:
    timestamps = [
        (datetime(2024, 7, 1) + timedelta(hours=index)).isoformat() for index in range(4)
    ]
    return {
        "timestamps": timestamps,
        "rainfall_values": [10.0, 20.0, 10.0, 0.0],
    }


def _optimization_rainfall_payload() -> dict[str, object]:
    timestamps = [
        (datetime(2024, 7, 1) + timedelta(hours=index)).isoformat() for index in range(6)
    ]
    return {
        "timestamps": timestamps,
        "rainfall_values": [4000.0] * 6,
    }


def test_plugin_discovery_and_preview_tools(sample_reservoir_spec) -> None:
    mcp = _FakeMCP()
    snapshot_service = SnapshotService()
    snapshot_service.create_initial_snapshot("res1", sample_reservoir_spec, 165.0, 100.0)
    plugin_manager = PluginManager()

    setup_plugin_tools(mcp, plugin_manager, snapshot_service)

    listed = mcp.tools["list_plugins"]()
    assert listed["count"] >= 3
    described = mcp.tools["describe_plugin"](
        plugin_kind="input",
        plugin_name="simple_rainfall_runoff",
    )
    assert described["plugin_name"] == "simple_rainfall_runoff"
    resolved = mcp.tools["resolve_plugins_for_task"](
        forecast_data=_rainfall_payload(),
    )
    assert resolved["status"] == "executable"
    assert resolved["selected"]["input"] == "simple_rainfall_runoff"
    unified_preview = mcp.tools["preview_plugin"](
        plugin_kind="input",
        plugin_name="simple_rainfall_runoff",
        plugin_config={"runoff_coefficient": 0.5, "lag_steps": 0},
        reservoir_id="res1",
        forecast_data=_rainfall_payload(),
    )
    assert unified_preview["generated_inflow"]["variable"] == "inflow"


def test_simulate_program_and_rolling_ops_accept_plugin_bundle(sample_reservoir_spec) -> None:
    mcp = _FakeMCP()
    snapshot_service = SnapshotService()
    program_service = ProgramService()
    plugin_manager = PluginManager()
    simulation_service = SimulationService(
        sample_reservoir_spec,
        program_service.get_module_registry(),
        plugin_manager=plugin_manager,
    )
    evaluation_service = EvaluationService(sample_reservoir_spec)
    optimization_service = OptimizationService(
        sample_reservoir_spec,
        program_service,
        plugin_manager=plugin_manager,
    )
    rolling_ops_service = RollingOpsService(
        program_service=program_service,
        simulation_service=simulation_service,
        evaluation_service=evaluation_service,
        optimization_service=optimization_service,
        snapshot_service=snapshot_service,
        repository=Repository(":memory:"),
    )

    state = snapshot_service.create_initial_snapshot("res1", sample_reservoir_spec, 165.0, 100.0)
    snapshot_service.update_snapshot(
        "res1",
        state.copy_with_update(timestamp=datetime(2024, 7, 1, 0, 0, 0)),
    )
    program = program_service.create_program(
        name="tool_program",
        time_horizon={
            "start": datetime(2024, 7, 1, 0, 0, 0),
            "end": datetime(2024, 7, 1, 3, 0, 0),
            "time_step": 3600,
        },
        module_configs=[{"module_type": "constant_release", "parameters": {"target_release": 50.0}}],
    )

    setup_simulation_tools(mcp, simulation_service, program_service, snapshot_service)
    setup_rolling_ops_tools(mcp, rolling_ops_service)

    plugin_bundle = {
        "input": {
            "name": "simple_rainfall_runoff",
            "config": {"runoff_coefficient": 0.5, "lag_steps": 0},
        },
        "post": {
            "name": "muskingum_routing",
            "config": {"k": 3.0, "x": 0.2, "dt_hours": 1.0},
        },
    }

    simulation_payload = mcp.tools["simulate_program"](
        program_id=program.id,
        reservoir_id="res1",
        forecast_data=_rainfall_payload(),
        plugin_bundle=plugin_bundle,
    )
    assert "plugin_results" in simulation_payload
    assert "input" in simulation_payload["plugin_results"]
    assert "post" in simulation_payload["plugin_results"]

    rolling_payload = mcp.tools["optimize_release_plan"](
        reservoir_id="res1",
        context_id="ctx1",
        forecast_data=_optimization_rainfall_payload(),
        constraints={"ecological_min_flow": 50.0, "max_release": 5000.0},
        task_constraints={"target_level": 165.0, "target_tolerance": 0.2},
        plugin_bundle=plugin_bundle,
    )
    assert "plugin_results" in rolling_payload["summary"]
