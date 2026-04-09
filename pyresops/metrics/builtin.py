"""Built-in metric evaluators."""

from __future__ import annotations

from typing import Any

from ..domain.constraint import ConstraintSet
from ..domain.reservoir import ReservoirSpec
from ..domain.result import SimulationResult
from .base import MetricEvaluator
from .registry import MetricRegistry


class FloodControlMetric(MetricEvaluator):
    metric_name = "flood"

    def evaluate(
        self,
        *,
        spec: ReservoirSpec,
        result: SimulationResult,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        if result.max_level <= spec.flood_limit_level:
            return 100.0
        if result.max_level <= spec.design_flood_level:
            excess = result.max_level - spec.flood_limit_level
            range_width = spec.design_flood_level - spec.flood_limit_level
            return max(0.0, 100.0 - 50.0 * (excess / range_width))
        return 0.0


class WaterSupplyMetric(MetricEvaluator):
    metric_name = "supply"

    def evaluate(
        self,
        *,
        spec: ReservoirSpec,
        result: SimulationResult,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        if result.min_level >= spec.normal_level:
            return 100.0
        if result.min_level >= spec.dead_level:
            margin = result.min_level - spec.dead_level
            range_width = spec.normal_level - spec.dead_level
            return 50.0 + 50.0 * (margin / range_width)
        return 0.0


class PowerGenerationMetric(MetricEvaluator):
    metric_name = "power"

    def evaluate(
        self,
        *,
        spec: ReservoirSpec,
        result: SimulationResult,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        if not result.snapshots:
            return 0.0
        tailwater_level = float(proxy_options.get("tailwater_level", spec.dead_level))
        proxy_values = []
        proxy_ceiling = []
        for snapshot in result.snapshots:
            head = max(snapshot.level - tailwater_level, 0.0)
            proxy_values.append(snapshot.outflow * head)
            proxy_ceiling.append(spec.discharge_capacity.get_max_discharge(snapshot.level) * head)
        total_proxy = sum(proxy_values)
        total_ceiling = sum(proxy_ceiling)
        if total_ceiling <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * total_proxy / total_ceiling))


class EcologyMetric(MetricEvaluator):
    metric_name = "ecology"

    def evaluate(
        self,
        *,
        spec: ReservoirSpec,
        result: SimulationResult,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        if not result.snapshots:
            return 100.0

        env_min_flow = float(proxy_options.get("env_min_flow", 0.0))
        max_ramp_rate = proxy_options.get("max_ramp_rate")
        max_ramp_rate = float(max_ramp_rate) if max_ramp_rate is not None else None

        flow_penalty = 0.0
        if env_min_flow > 0:
            deficit_sum = sum(
                max(env_min_flow - snapshot.outflow, 0.0) for snapshot in result.snapshots
            )
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


class ComplianceMetric(MetricEvaluator):
    metric_name = "compliance"

    def evaluate(
        self,
        *,
        spec: ReservoirSpec,
        result: SimulationResult,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        if not constraint_set:
            return 100.0

        severity_penalty = {
            "info": 1.0,
            "warning": 3.0,
            "minor": 5.0,
            "major": 10.0,
            "critical": 20.0,
        }
        penalty = 0.0
        for constraint in constraint_set.enabled_constraints():
            weight = severity_penalty.get(constraint.severity, 10.0)
            if constraint.enforcement == "hard":
                weight *= 1.5
            penalty += weight

        return max(0.0, min(100.0, 100.0 - penalty))


def register_builtin_metrics(registry: MetricRegistry) -> None:
    """Register built-in metrics."""
    registry.register(FloodControlMetric.metric_name, FloodControlMetric)
    registry.register(WaterSupplyMetric.metric_name, WaterSupplyMetric)
    registry.register(PowerGenerationMetric.metric_name, PowerGenerationMetric)
    registry.register(EcologyMetric.metric_name, EcologyMetric)
    registry.register(ComplianceMetric.metric_name, ComplianceMetric)
