"""Built-in ecological constraints."""

from __future__ import annotations

from ..base import ConstraintEvaluator


class EcologicalMinFlowConstraint(ConstraintEvaluator):
    """Ecological minimum-flow guard."""

    constraint_type = "ecological_min_flow"

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        min_flow = self.constraint.parameters.get("min_flow")
        if min_flow is None:
            return []
        min_flow = float(min_flow)
        if outflow < min_flow:
            return [
                self._build_violation(
                    violation_type="ecological_flow_below",
                    scope="step",
                    step_index=step_index,
                    value=outflow,
                    limit=min_flow,
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        min_flow = self.constraint.parameters.get("min_flow")
        if min_flow is None:
            return None
        min_flow = float(min_flow)
        if outflow >= min_flow:
            return None
        return {
            "action": "clamp_outflow",
            "min_outflow": min_flow,
            "reason": "ecological minimum flow",
        }
