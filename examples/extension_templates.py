"""Minimal extension templates for constraint/rule/metric developers.

This file demonstrates the smallest working custom implementations and how to
register them into the runtime registries.
"""

from __future__ import annotations

from typing import Any

from pyresops.constraints import ConstraintRegistry
from pyresops.constraints.base import ConstraintEvaluator
from pyresops.domain.decision import ViolationRecord
from pyresops.domain.policy import ExecutionContext
from pyresops.metrics import MetricRegistry
from pyresops.metrics.base import MetricEvaluator
from pyresops.rules import RuleRegistry
from pyresops.rules.base import RuleEvaluator


class DemoOutflowCeilingConstraint(ConstraintEvaluator):
    """Example custom step-constraint: enforce max outflow."""

    constraint_type = "demo_outflow_ceiling"

    def validate_step(
        self,
        *,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
        context: dict[str, Any] | None = None,
    ) -> list[ViolationRecord]:
        ceiling = float(self.constraint.parameters.get("ceiling", float("inf")))
        if outflow <= ceiling:
            return []
        return [
            self._build_violation(
                violation_type="flow_exceeded",
                scope="step",
                step_index=step_index,
                value=outflow,
                limit=ceiling,
            )
        ]


class DemoHighInflowRule(RuleEvaluator):
    """Example custom rule: clamp outflow when inflow is high."""

    def match(self, context: ExecutionContext) -> bool:
        threshold = float(self.rule.metadata.get("threshold", 9000.0))
        return context.inflow >= threshold


class DemoStabilityMetric(MetricEvaluator):
    """Example custom metric: outflow smoothness score."""

    metric_name = "demo_stability"

    def evaluate(self, *, spec, result, constraint_set, proxy_options) -> float:
        if len(result.snapshots) < 2:
            return 100.0

        deltas = [
            abs(curr.outflow - prev.outflow)
            for prev, curr in zip(result.snapshots[:-1], result.snapshots[1:])
        ]
        avg_delta = sum(deltas) / len(deltas)
        return max(0.0, min(100.0, 100.0 - avg_delta / 100.0))


def register_demo_extensions(
    *,
    constraint_registry: ConstraintRegistry,
    rule_registry: RuleRegistry,
    metric_registry: MetricRegistry,
) -> None:
    """Register all demo extensions into registries."""
    constraint_registry.register(
        DemoOutflowCeilingConstraint.constraint_type, DemoOutflowCeilingConstraint
    )
    rule_registry.register("demo_rule", DemoHighInflowRule)
    metric_registry.register(DemoStabilityMetric.metric_name, DemoStabilityMetric)
