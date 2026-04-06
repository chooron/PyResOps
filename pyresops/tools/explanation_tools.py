"""Explanation and interpretation tools."""

from typing import Any

from ..services import EvaluationService, ExplanationService, ProgramService, SimulationService


def setup_explanation_tools(
    mcp_server: Any,
    explanation_service: ExplanationService,
    program_service: ProgramService,
    simulation_service: SimulationService,
    evaluation_service: EvaluationService,
) -> None:
    """Setup explanation-related MCP tools."""

    @mcp_server.tool()
    def explain_program(program_id: str) -> dict[str, Any]:
        """
        解释调度方案的决策逻辑.

        Args:
            program_id: 调度方案ID

        Returns:
            解释报告
        """
        # 获取方案
        program = program_service.get_program(program_id)
        if not program:
            return {"error": f"Program not found: {program_id}"}

        # 获取仿真和评估结果 (如果存在)
        simulation_result = simulation_service.get_result(program_id)
        evaluation_result = None

        if simulation_result:
            evaluation_result = evaluation_service.evaluate(simulation_result)

        # 生成解释
        explanation = explanation_service.explain_program(
            program, simulation_result, evaluation_result
        )

        return explanation
