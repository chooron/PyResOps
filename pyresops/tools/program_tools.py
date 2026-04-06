"""Program management tools."""

from typing import Any

from ..services import ProgramService


def setup_program_tools(mcp_server: Any, program_service: ProgramService) -> None:
    """Setup program-related MCP tools."""

    @mcp_server.tool()
    def list_operation_modules() -> list[dict[str, Any]]:
        """
        列出所有可用的操作模块.

        Returns:
            操作模块信息列表
        """
        return program_service.list_available_modules()

    @mcp_server.tool()
    def generate_dispatch_program(
        name: str,
        start_time: str,
        end_time: str,
        time_step: int,
        modules: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        生成调度方案.

        Args:
            name: 方案名称
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            time_step: 时间步长 (秒)
            modules: 模块配置列表

        Returns:
            调度方案信息
        """
        from datetime import datetime
        from ..domain.program import TimeHorizon

        time_horizon = TimeHorizon(
            start=datetime.fromisoformat(start_time),
            end=datetime.fromisoformat(end_time),
            time_step=time_step,
        )

        program = program_service.create_program(name, time_horizon, modules)

        return {
            "program_id": program.id,
            "name": program.name,
            "created_at": program.created_at.isoformat(),
            "time_horizon": {
                "start": program.time_horizon.start.isoformat(),
                "end": program.time_horizon.end.isoformat(),
                "time_step": program.time_horizon.time_step,
            },
            "module_count": len(program.module_sequence),
        }

    @mcp_server.tool()
    def list_programs() -> list[dict[str, Any]]:
        """
        列出所有调度方案.

        Returns:
            方案列表
        """
        programs = program_service.list_programs()

        return [
            {
                "program_id": p.id,
                "name": p.name,
                "created_at": p.created_at.isoformat(),
                "module_count": len(p.module_sequence),
            }
            for p in programs
        ]
