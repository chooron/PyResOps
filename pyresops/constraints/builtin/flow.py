"""Built-in flow constraints."""

from __future__ import annotations

from ..base import ConstraintEvaluator


class FlowMaxConstraint(ConstraintEvaluator):
    """Maximum outflow constraint."""

    constraint_type = "flow_max"

    def validate_global(self, *, result, context=None):
        max_flow_limit = float(self.constraint.parameters.get("max_flow", float("inf")))
        if not result.snapshots:
            return []

        max_outflow = max(snapshot.outflow for snapshot in result.snapshots)
        if max_outflow > max_flow_limit:
            return [
                self._build_violation(
                    violation_type="flow_exceeded",
                    scope="global",
                    value=max_outflow,
                    limit=max_flow_limit,
                )
            ]
        return []

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        max_flow_limit = float(self.constraint.parameters.get("max_flow", float("inf")))
        if outflow > max_flow_limit:
            return [
                self._build_violation(
                    violation_type="flow_exceeded",
                    scope="step",
                    step_index=step_index,
                    value=outflow,
                    limit=max_flow_limit,
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        max_flow_limit = float(self.constraint.parameters.get("max_flow", float("inf")))
        if outflow > max_flow_limit:
            return {
                "action": "clamp_outflow",
                "max_outflow": max_flow_limit,
                "reason": "flow exceeds max limit",
            }
        return None


class FlowMinConstraint(ConstraintEvaluator):
    """Minimum outflow constraint."""

    constraint_type = "flow_min"

    def validate_global(self, *, result, context=None):
        min_flow_limit = float(self.constraint.parameters.get("min_flow", float("-inf")))
        if not result.snapshots:
            return []

        min_outflow = min(snapshot.outflow for snapshot in result.snapshots)
        if min_outflow < min_flow_limit:
            return [
                self._build_violation(
                    violation_type="flow_below",
                    scope="global",
                    value=min_outflow,
                    limit=min_flow_limit,
                )
            ]
        return []

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        min_flow_limit = float(self.constraint.parameters.get("min_flow", float("-inf")))
        if outflow < min_flow_limit:
            return [
                self._build_violation(
                    violation_type="flow_below",
                    scope="step",
                    step_index=step_index,
                    value=outflow,
                    limit=min_flow_limit,
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        min_flow_limit = float(self.constraint.parameters.get("min_flow", float("-inf")))
        if outflow < min_flow_limit:
            return {
                "action": "clamp_outflow",
                "min_outflow": min_flow_limit,
                "reason": "flow below min limit",
            }
        return None


class WaterSupplyConstraint(ConstraintEvaluator):
    """Water-supply demand constraint (global)."""

    constraint_type = "water_supply"

    def validate_global(self, *, result, context=None):
        demand = float(self.constraint.parameters.get("demand", 0.0))
        if result.avg_outflow < demand:
            return [
                self._build_violation(
                    violation_type="water_supply_insufficient",
                    scope="global",
                    value=result.avg_outflow,
                    limit=demand,
                )
            ]
        return []
