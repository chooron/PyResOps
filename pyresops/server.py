"""FastMCP server assembly for pyresops."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
)
from .plugins import PluginManager
from .providers import ReservoirBootstrap, ReservoirYamlError, load_reservoir_bootstrap_from_yaml
from .services import (
    EvaluationService,
    ExplanationService,
    OptimizationService,
    ProgramService,
    RollingOpsService,
    SimulationService,
    SnapshotService,
)
from .storage import Repository
from .tools import (
    setup_evaluation_tools,
    setup_explanation_tools,
    setup_plugin_tools,
    setup_program_tools,
    setup_rolling_ops_tools,
    setup_simulation_tools,
    setup_snapshot_tools,
)


DEFAULT_RESERVOIR_CONFIG_PATH = Path("configs/default_reservoir.yaml")


@dataclass
class ServerRuntime:
    """Bundled service objects used by the packaged MCP server."""

    reservoir_spec: ReservoirSpec
    snapshot_service: SnapshotService
    program_service: ProgramService
    plugin_manager: PluginManager
    simulation_service: SimulationService
    evaluation_service: EvaluationService
    explanation_service: ExplanationService
    optimization_service: OptimizationService
    repository: Repository
    rolling_ops_service: RollingOpsService
    bootstrap_context: dict[str, object] | None


def create_demo_reservoir_spec() -> ReservoirSpec:
    """Create a built-in demo reservoir when no config is provided."""
    return ReservoirSpec(
        id="demo_reservoir",
        name="Demo Reservoir",
        dead_level=150.0,
        normal_level=175.0,
        flood_limit_level=145.0,
        design_flood_level=180.0,
        check_flood_level=185.0,
        total_capacity=39.3,
        flood_capacity=22.15,
        level_storage_curve=LevelStorageCurve(
            levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
            storages=[0.0, 10.0, 20.0, 30.0, 39.3, 51.6],
        ),
        discharge_capacity=DischargeCapacity(
            levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
            max_discharges=[0.0, 5000.0, 10000.0, 15000.0, 20000.0, 30000.0],
        ),
    )


def load_reservoir_spec(
    reservoir_config_path: str | os.PathLike[str] | None = None,
) -> tuple[ReservoirSpec, dict[str, object] | None]:
    """Load a reservoir spec from explicit path, env, default path, or demo fallback."""
    if reservoir_config_path:
        bootstrap = load_reservoir_bootstrap_from_yaml(reservoir_config_path)
        return bootstrap.spec, {"bootstrap": bootstrap, "config_path": str(reservoir_config_path)}

    configured_path = os.getenv("PYRESOPS_RESERVOIR_CONFIG")
    if configured_path:
        bootstrap = load_reservoir_bootstrap_from_yaml(configured_path)
        return bootstrap.spec, {"bootstrap": bootstrap, "config_path": configured_path}

    if DEFAULT_RESERVOIR_CONFIG_PATH.exists():
        bootstrap = load_reservoir_bootstrap_from_yaml(DEFAULT_RESERVOIR_CONFIG_PATH)
        return (
            bootstrap.spec,
            {
                "bootstrap": bootstrap,
                "config_path": str(DEFAULT_RESERVOIR_CONFIG_PATH),
            },
        )

    return create_demo_reservoir_spec(), None


def build_runtime(
    *,
    reservoir_config_path: str | os.PathLike[str] | None = None,
    data_dir: str | os.PathLike[str] = "data",
) -> ServerRuntime:
    """Build the default pyresops runtime bundle used by MCP servers."""
    try:
        reservoir_spec, bootstrap_context = load_reservoir_spec(reservoir_config_path)
    except ReservoirYamlError as exc:
        raise RuntimeError(f"Failed to load reservoir configuration: {exc}") from exc

    snapshot_service = SnapshotService()
    program_service = ProgramService()
    plugin_manager = PluginManager()
    default_plugin_bundle = None
    if bootstrap_context and "bootstrap" in bootstrap_context:
        bootstrap = bootstrap_context["bootstrap"]
        if isinstance(bootstrap, ReservoirBootstrap) and bootstrap.execution is not None:
            default_plugin_bundle = bootstrap.execution.plugins

    simulation_service = SimulationService(
        reservoir_spec,
        program_service.get_module_registry(),
        plugin_manager=plugin_manager,
        default_plugin_bundle=default_plugin_bundle,
    )
    evaluation_service = EvaluationService(reservoir_spec)
    explanation_service = ExplanationService()
    optimization_service = OptimizationService(
        reservoir_spec,
        program_service,
        plugin_manager=plugin_manager,
        default_plugin_bundle=default_plugin_bundle,
    )

    resolved_data_dir = Path(data_dir)
    resolved_data_dir.mkdir(parents=True, exist_ok=True)
    repository = Repository(str(resolved_data_dir / "pyresops.db"))
    rolling_ops_service = RollingOpsService(
        program_service=program_service,
        simulation_service=simulation_service,
        evaluation_service=evaluation_service,
        optimization_service=optimization_service,
        snapshot_service=snapshot_service,
        repository=repository,
    )

    if bootstrap_context and "bootstrap" in bootstrap_context:
        bootstrap = bootstrap_context["bootstrap"]
        if not isinstance(bootstrap, ReservoirBootstrap):
            raise RuntimeError("Invalid bootstrap object type")
        initial_state = bootstrap.create_initial_state()
        snapshot_service.update_snapshot(reservoir_spec.id, initial_state)
    else:
        snapshot_service.create_initial_snapshot(
            reservoir_id=reservoir_spec.id,
            spec=reservoir_spec,
            level=165.0,
            inflow=8000.0,
        )

    return ServerRuntime(
        reservoir_spec=reservoir_spec,
        snapshot_service=snapshot_service,
        program_service=program_service,
        plugin_manager=plugin_manager,
        simulation_service=simulation_service,
        evaluation_service=evaluation_service,
        explanation_service=explanation_service,
        optimization_service=optimization_service,
        repository=repository,
        rolling_ops_service=rolling_ops_service,
        bootstrap_context=bootstrap_context,
    )


def register_standard_tools(mcp_server: Any, runtime: ServerRuntime) -> None:
    """Register the standard pyresops tool surface on an MCP server."""
    setup_snapshot_tools(mcp_server, runtime.snapshot_service)
    setup_program_tools(mcp_server, runtime.program_service)
    setup_simulation_tools(
        mcp_server,
        runtime.simulation_service,
        runtime.program_service,
        runtime.snapshot_service,
    )
    setup_evaluation_tools(mcp_server, runtime.evaluation_service, runtime.simulation_service)
    setup_explanation_tools(
        mcp_server,
        runtime.explanation_service,
        runtime.program_service,
        runtime.simulation_service,
        runtime.evaluation_service,
    )
    setup_plugin_tools(mcp_server, runtime.plugin_manager, runtime.snapshot_service)
    setup_rolling_ops_tools(mcp_server, runtime.rolling_ops_service)


def create_server(
    *,
    name: str = "res-ops-mcp",
    reservoir_config_path: str | os.PathLike[str] | None = None,
    data_dir: str | os.PathLike[str] = "data",
) -> FastMCP:
    """Create a packaged FastMCP server with the standard pyresops tool surface."""
    runtime = build_runtime(
        reservoir_config_path=reservoir_config_path,
        data_dir=data_dir,
    )
    mcp_server = FastMCP(name)
    register_standard_tools(mcp_server, runtime)
    return mcp_server


mcp = create_server()


if __name__ == "__main__":
    mcp.run()
