"""Evaluation service for assessing simulation results."""

from ..domain.constraint import ConstraintSet
from ..domain.reservoir import ReservoirSpec
from ..domain.result import EvaluationResult, SimulationResult, StepScore
from ..core.validator import ConstraintValidator


class EvaluationService:
    """评估服务 (Evaluation Service)."""

    def __init__(self, spec: ReservoirSpec):
        """初始化评估服务."""
        self.spec = spec

    def evaluate(
        self,
        result: SimulationResult,
        constraint_set: ConstraintSet | None = None,
        include_step_scores: bool = False,
    ) -> EvaluationResult:
        """
        评估仿真结果.

        Args:
            result: 仿真结果
            constraint_set: 约束集合 (可选)
            include_step_scores: 是否包含逐步评分

        Returns:
            评估结果
        """
        # 约束校核
        violations = []
        validator = None
        if constraint_set:
            validator = ConstraintValidator(constraint_set)
            violations = validator.validate_simulation(result)

        # 计算评分
        flood_control_score = self._evaluate_flood_control(result)
        water_supply_score = self._evaluate_water_supply(result)

        # 综合评分 (简化版本: 加权平均)
        overall_score = 0.5 * flood_control_score + 0.5 * water_supply_score

        # 约束违反惩罚
        if violations:
            overall_score *= 0.5

        # 逐步评分
        step_scores = []
        if include_step_scores:
            step_scores = self._compute_step_scores(result, validator)

        return EvaluationResult(
            program_id=result.program_id,
            simulation_result_id=result.program_id,
            flood_control_score=flood_control_score,
            water_supply_score=water_supply_score,
            overall_score=overall_score,
            constraint_violations=violations,
            step_scores=step_scores,
        )

    def _compute_step_scores(
        self,
        result: SimulationResult,
        validator: ConstraintValidator | None,
    ) -> list[StepScore]:
        """计算逐步评分."""
        step_scores: list[StepScore] = []
        total_capacity = self.spec.total_capacity
        dead_level = self.spec.dead_level
        flood_limit = self.spec.flood_limit_level
        normal_level = self.spec.normal_level

        for idx, snap in enumerate(result.snapshots):
            # 单步风险分: 水位越接近洪水位风险越高
            if snap.level <= flood_limit:
                risk_score = 100.0
            elif snap.level <= self.spec.design_flood_level:
                excess = snap.level - flood_limit
                range_w = self.spec.design_flood_level - flood_limit
                risk_score = max(0.0, 100.0 - 80.0 * (excess / range_w))
            else:
                risk_score = 0.0

            # 过程约束分: 该步有无违反
            constraint_score = 100.0
            step_violations = []
            if validator:
                step_violations = validator.validate_step(
                    idx, snap.level, snap.inflow, snap.outflow
                )
                if step_violations:
                    constraint_score = max(0.0, 100.0 - 20.0 * len(step_violations))

            # 阶段性收益分: 供水能力评估
            if snap.level >= normal_level:
                benefit_score = 100.0
            elif snap.level >= dead_level:
                margin = snap.level - dead_level
                range_w = normal_level - dead_level
                benefit_score = 50.0 + 50.0 * (margin / range_w)
            else:
                benefit_score = 0.0

            step_scores.append(
                StepScore(
                    step_index=idx,
                    timestamp=snap.timestamp,
                    risk_score=risk_score,
                    constraint_score=constraint_score,
                    benefit_score=benefit_score,
                    violations=step_violations,
                )
            )

        return step_scores

    def _evaluate_flood_control(self, result: SimulationResult) -> float:
        """评估防洪效果."""
        if result.max_level <= self.spec.flood_limit_level:
            return 100.0
        elif result.max_level <= self.spec.design_flood_level:
            excess = result.max_level - self.spec.flood_limit_level
            range_width = self.spec.design_flood_level - self.spec.flood_limit_level
            return max(0.0, 100.0 - 50.0 * (excess / range_width))
        else:
            return 0.0

    def _evaluate_water_supply(self, result: SimulationResult) -> float:
        """评估供水效果."""
        if result.min_level >= self.spec.normal_level:
            return 100.0
        elif result.min_level >= self.spec.dead_level:
            margin = result.min_level - self.spec.dead_level
            range_width = self.spec.normal_level - self.spec.dead_level
            return 50.0 + 50.0 * (margin / range_width)
        else:
            return 0.0
