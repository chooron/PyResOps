"""FastMCP server for res-ops-mcp."""

from pathlib import Path

from fastmcp import FastMCP

from .domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
)
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
    setup_program_tools,
    setup_rolling_ops_tools,
    setup_simulation_tools,
    setup_snapshot_tools,
)

# 创建 FastMCP 应用
mcp = FastMCP("res-ops-mcp")


# 全局服务实例 (示例配置)
def create_demo_reservoir_spec() -> ReservoirSpec:
    """创建示例水库规范."""
    return ReservoirSpec(
        id="demo_reservoir",
        name="示例水库",
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


# 初始化服务
reservoir_spec = create_demo_reservoir_spec()
snapshot_service = SnapshotService()
program_service = ProgramService()
simulation_service = SimulationService(reservoir_spec, program_service.get_module_registry())
evaluation_service = EvaluationService(reservoir_spec)
explanation_service = ExplanationService()
optimization_service = OptimizationService(reservoir_spec, program_service)
data_dir = Path("data")
data_dir.mkdir(parents=True, exist_ok=True)
repository = Repository(str(data_dir / "res_ops.db"))
rolling_ops_service = RollingOpsService(
    program_service=program_service,
    simulation_service=simulation_service,
    evaluation_service=evaluation_service,
    optimization_service=optimization_service,
    snapshot_service=snapshot_service,
    repository=repository,
)

# 创建初始快照 (示例)
snapshot_service.create_initial_snapshot(
    reservoir_id="demo_reservoir", spec=reservoir_spec, level=165.0, inflow=8000.0
)

# 注册 MCP 工具
setup_snapshot_tools(mcp, snapshot_service)
setup_program_tools(mcp, program_service)
setup_simulation_tools(mcp, simulation_service, program_service, snapshot_service)
setup_evaluation_tools(mcp, evaluation_service, simulation_service)
setup_explanation_tools(
    mcp, explanation_service, program_service, simulation_service, evaluation_service
)
setup_rolling_ops_tools(mcp, rolling_ops_service)


if __name__ == "__main__":
    # 运行 MCP 服务器
    mcp.run()
