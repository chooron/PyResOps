"""Explanation service for generating interpretable reports."""

from typing import Any

from ..domain.program import DispatchProgram
from ..domain.result import SimulationResult, EvaluationResult


class ExplanationService:
    """解释服务 (Explanation Service)."""

    def explain_program(
        self,
        program: DispatchProgram,
        simulation_result: SimulationResult | None = None,
        evaluation_result: EvaluationResult | None = None,
    ) -> dict[str, Any]:
        """
        生成方案解释.

        Args:
            program: 调度方案
            simulation_result: 仿真结果 (可选)
            evaluation_result: 评估结果 (可选)

        Returns:
            解释报告
        """
        explanation: dict[str, Any] = {
            "program_id": program.id,
            "program_name": program.name,
            "summary": self._generate_summary(program),
            "module_sequence": self._explain_modules(program),
        }

        if simulation_result:
            explanation["simulation_summary"] = {
                "max_level": simulation_result.max_level,
                "min_level": simulation_result.min_level,
                "avg_outflow": simulation_result.avg_outflow,
                "total_steps": len(simulation_result.snapshots),
            }

        if evaluation_result:
            explanation["evaluation_summary"] = {
                "overall_score": evaluation_result.overall_score,
                "flood_control_score": evaluation_result.flood_control_score,
                "water_supply_score": evaluation_result.water_supply_score,
                "violations_count": len(evaluation_result.constraint_violations),
            }

        return explanation

    def _generate_summary(self, program: DispatchProgram) -> str:
        """生成方案摘要."""
        module_count = len(program.module_sequence)
        duration = (program.time_horizon.end - program.time_horizon.start).total_seconds() / 3600

        return (
            f"调度方案 '{program.name}' 包含 {module_count} 个操作模块, "
            f"调度时长 {duration:.1f} 小时."
        )

    def _explain_modules(self, program: DispatchProgram) -> list[dict[str, Any]]:
        """解释模块序列."""
        explanations = []
        for idx, module in enumerate(program.module_sequence):
            explanations.append(
                {
                    "index": idx,
                    "module_type": module.module_type,
                    "parameters": module.parameters,
                    "active_period": (
                        f"{module.active_period[0]} ~ {module.active_period[1]}"
                        if module.active_period
                        else "全时段"
                    ),
                }
            )
        return explanations
