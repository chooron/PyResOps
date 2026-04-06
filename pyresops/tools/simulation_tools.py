"""Simulation execution tools."""

from typing import Any

from ..services import ProgramService, SimulationService, SnapshotService


def setup_simulation_tools(
    mcp_server: Any,
    simulation_service: SimulationService,
    program_service: ProgramService,
    snapshot_service: SnapshotService,
) -> None:
    """Setup simulation-related MCP tools."""

    @mcp_server.tool()
    def simulate_program(
        program_id: str,
        reservoir_id: str,
        forecast_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        仿真调度方案.

        Args:
            program_id: 调度方案ID
            reservoir_id: 水库ID
            forecast_data: 预报数据 (包含 timestamps 和 inflow_values)

        Returns:
            仿真结果摘要
        """
        from datetime import datetime
        from ..domain.forecast import ForecastBundle, ForecastSeries

        # 获取方案和初始状态
        program = program_service.get_program(program_id)
        if not program:
            return {"error": f"Program not found: {program_id}"}

        initial_state = snapshot_service.get_snapshot(reservoir_id)
        if not initial_state:
            return {"error": f"Snapshot not found for reservoir: {reservoir_id}"}

        # 构建预报数据
        timestamps = [datetime.fromisoformat(ts) for ts in forecast_data["timestamps"]]
        inflow_values = forecast_data["inflow_values"]

        forecast = ForecastBundle(
            forecast_time=datetime.now(),
            series=[
                ForecastSeries(
                    variable="inflow", timestamps=timestamps, values=inflow_values, unit="m³/s"
                )
            ],
        )

        # 运行仿真
        result = simulation_service.run_simulation(program, initial_state, forecast)

        return {
            "program_id": result.program_id,
            "start_time": result.start_time.isoformat(),
            "end_time": result.end_time.isoformat(),
            "max_level": result.max_level,
            "min_level": result.min_level,
            "avg_outflow": result.avg_outflow,
            "snapshot_count": len(result.snapshots),
        }
