"""Evaluation service for assessing simulation results."""

from __future__ import annotations

from typing import Any

from ..core.validator import ConstraintValidator
from ..domain.constraint import ConstraintSet
from ..domain.reservoir import ReservoirSpec
from ..domain.result import EvaluationResult, SimulationResult, StepScore
from ..metrics import MetricRegistry, register_builtin_metrics


class EvaluationService:
    """评估服务 (Evaluation Service)."""

    def __init__(self, spec: ReservoirSpec):
        """初始化评估服务."""
        self.spec = spec
        self.metric_registry = MetricRegistry()
        register_builtin_metrics(self.metric_registry)

    def register_metric(self, metric_name: str, factory: Any) -> None:
        """Register custom metric evaluator factory."""
        self.metric_registry.register(metric_name, factory)

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
        resolved_proxy_options = dict(proxy_options)
        resolved_proxy_options.setdefault("tailwater_level", self.spec.dead_level)
        resolved_proxy_options.setdefault(
            "env_min_flow",
            self._resolve_env_min_flow(constraint_set, resolved_proxy_options),
        )

        metric_values = {}
        for metric_name, evaluator in self.metric_registry.create_all().items():
            metric_values[metric_name] = evaluator.evaluate(
                spec=self.spec,
                result=result,
                constraint_set=constraint_set,
                proxy_options=resolved_proxy_options,
            )

        flood_control_score = metric_values.get("flood", 0.0)
        water_supply_score = metric_values.get("supply", 0.0)
        power_generation_score = metric_values.get("power", 0.0)
        ecological_score = metric_values.get("ecology", 0.0)

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
            additional_scores={
                key: value
                for key, value in metric_values.items()
                if key not in {"flood", "supply", "power", "ecology"}
            },
            metadata={
                "weights": score_weights,
                "proxy_options": {
                    "tailwater_level": float(resolved_proxy_options["tailwater_level"]),
                    "env_min_flow": float(resolved_proxy_options["env_min_flow"]),
                    "max_ramp_rate": resolved_proxy_options.get("max_ramp_rate"),
                },
                "metric_values": metric_values,
            },
        )

    def _compute_step_scores(
        self,
        result: SimulationResult,
        validator: ConstraintValidator | None,
    ) -> list[StepScore]:
        """计算逐步评分."""
        step_scores: list[StepScore] = []
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
                    idx,
                    snap.level,
                    snap.inflow,
                    snap.outflow,
                    previous_outflow=(result.snapshots[idx - 1].outflow if idx > 0 else None),
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
