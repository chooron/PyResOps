"""Evaluation and comparison tools."""

from typing import Any

from ..services import EvaluationService, SimulationService


def setup_evaluation_tools(
    mcp_server: Any,
    evaluation_service: EvaluationService,
    simulation_service: SimulationService,
) -> None:
    """Setup evaluation-related MCP tools."""

    @mcp_server.tool()
    def evaluate_program(program_id: str) -> dict[str, Any]:
        """
        评估调度方案.

        Args:
            program_id: 调度方案ID

        Returns:
            评估结果
        """
        # 获取仿真结果
        result = simulation_service.get_result(program_id)
        if not result:
            return {"error": f"Simulation result not found for program: {program_id}"}

        # 执行评估
        evaluation = evaluation_service.evaluate(result)

        return {
            "program_id": evaluation.program_id,
            "overall_score": evaluation.overall_score,
            "flood_control_score": evaluation.flood_control_score,
            "water_supply_score": evaluation.water_supply_score,
            "power_generation_score": evaluation.power_generation_score,
            "ecological_score": evaluation.ecological_score,
            "violations_count": len(evaluation.constraint_violations),
            "constraint_violations": evaluation.constraint_violations,
        }

    @mcp_server.tool()
    def compare_programs(program_ids: list[str]) -> dict[str, Any]:
        """
        比较多个调度方案.

        Args:
            program_ids: 方案ID列表

        Returns:
            比较结果
        """
        comparisons = []

        for program_id in program_ids:
            result = simulation_service.get_result(program_id)
            if not result:
                continue

            evaluation = evaluation_service.evaluate(result)

            comparisons.append(
                {
                    "program_id": program_id,
                    "overall_score": evaluation.overall_score,
                    "max_level": result.max_level,
                    "min_level": result.min_level,
                    "avg_outflow": result.avg_outflow,
                    "violations_count": len(evaluation.constraint_violations),
                }
            )

        # 排序: 按综合评分降序
        comparisons.sort(key=lambda x: x["overall_score"], reverse=True)

        return {
            "comparison_count": len(comparisons),
            "best_program": comparisons[0]["program_id"] if comparisons else None,
            "comparisons": comparisons,
        }
