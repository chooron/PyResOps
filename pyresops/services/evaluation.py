"""Evaluation service for assessing simulation results."""

from typing import Any

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
        weights: dict[str, float] | None = None,
        proxy_options: dict[str, Any] | None = None,
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

        proxy_options = proxy_options or {}

        # 计算评分
        flood_control_score = self._evaluate_flood_control(result)
        water_supply_score = self._evaluate_water_supply(result)
        tailwater_level = float(proxy_options.get("tailwater_level", self.spec.dead_level))
        env_min_flow = self._resolve_env_min_flow(constraint_set, proxy_options)
        max_ramp_rate = proxy_options.get("max_ramp_rate")
        max_ramp_rate = float(max_ramp_rate) if max_ramp_rate is not None else None
        power_generation_score = self._evaluate_power_generation(result, tailwater_level)
        ecological_score = self._evaluate_ecology(result, env_min_flow, max_ramp_rate)

        # 综合评分
        score_weights = {
            "flood": 0.45,
            "supply": 0.25,
            "power": 0.20,
            "ecology": 0.10,
        }
        if weights:
            score_weights.update(weights)

        total_weight = sum(score_weights.values())
        if total_weight <= 0:
            raise ValueError("evaluation weights must have positive sum")

        overall_score = (
            score_weights["flood"] * flood_control_score
            + score_weights["supply"] * water_supply_score
            + score_weights["power"] * power_generation_score
            + score_weights["ecology"] * ecological_score
        ) / total_weight

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
            power_generation_score=power_generation_score,
            ecological_score=ecological_score,
            overall_score=overall_score,
            constraint_violations=violations,
            step_scores=step_scores,
            metadata={
                "weights": score_weights,
                "proxy_options": {
                    "tailwater_level": tailwater_level,
                    "env_min_flow": env_min_flow,
                    "max_ramp_rate": max_ramp_rate,
                },
            },
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

    def _evaluate_power_generation(self, result: SimulationResult, tailwater_level: float) -> float:
        """Evaluate power proxy by outflow-head product (0-100)."""
        if not result.snapshots:
            return 0.0

        proxy_values = []
        proxy_ceiling = []
        for snap in result.snapshots:
            head = max(snap.level - tailwater_level, 0.0)
            proxy_values.append(snap.outflow * head)
            proxy_ceiling.append(self.spec.discharge_capacity.get_max_discharge(snap.level) * head)

        total_proxy = sum(proxy_values)
        total_ceiling = sum(proxy_ceiling)
        if total_ceiling <= 0:
            return 0.0

        return max(0.0, min(100.0, 100.0 * total_proxy / total_ceiling))

    def _evaluate_ecology(
        self,
        result: SimulationResult,
        env_min_flow: float,
        max_ramp_rate: float | None,
    ) -> float:
        """Evaluate ecology proxy with min-flow and optional ramp penalties."""
        if not result.snapshots:
            return 100.0

        flow_penalty = 0.0
        if env_min_flow > 0:
            deficit_sum = sum(max(env_min_flow - snap.outflow, 0.0) for snap in result.snapshots)
            max_deficit = env_min_flow * len(result.snapshots)
            if max_deficit > 0:
                flow_penalty = min(80.0, 100.0 * deficit_sum / max_deficit)

        ramp_penalty = 0.0
        if max_ramp_rate is not None and len(result.snapshots) > 1 and max_ramp_rate > 0:
            exceed_sum = 0.0
            for prev, curr in zip(result.snapshots[:-1], result.snapshots[1:]):
                exceed_sum += max(abs(curr.outflow - prev.outflow) - max_ramp_rate, 0.0)
            baseline = max_ramp_rate * (len(result.snapshots) - 1)
            if baseline > 0:
                ramp_penalty = min(40.0, 50.0 * exceed_sum / baseline)

        return max(0.0, min(100.0, 100.0 - flow_penalty - ramp_penalty))

    def _resolve_env_min_flow(
        self,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        """Resolve ecological minimum flow from explicit options or constraints."""
        if proxy_options.get("env_min_flow") is not None:
            return float(proxy_options["env_min_flow"])

        if not constraint_set:
            return 0.0

        for constraint in constraint_set.constraints:
            if constraint.constraint_type == "flow_min":
                return float(constraint.parameters.get("min_flow", 0.0))
        return 0.0
