"""Built-in ramp-rate constraints."""

from __future__ import annotations

from ..base import ConstraintEvaluator


class RampRateMaxConstraint(ConstraintEvaluator):
    """Maximum absolute ramp-rate constraint on outflow."""

    constraint_type = "ramp_rate_max"

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        context = context or {}
        max_ramp = self.constraint.parameters.get("max_ramp")
        if max_ramp is None:
            return []
        max_ramp = float(max_ramp)

        previous_outflow = context.get("previous_outflow")
        if previous_outflow is None:
            return []

        delta = abs(outflow - float(previous_outflow))
        if delta > max_ramp:
            return [
                self._build_violation(
                    violation_type="ramp_rate_exceeded",
                    scope="step",
                    step_index=step_index,
                    value=delta,
                    limit=max_ramp,
                    details={"previous_outflow": float(previous_outflow)},
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        context = context or {}
        max_ramp = self.constraint.parameters.get("max_ramp")
        previous_outflow = context.get("previous_outflow")
        if max_ramp is None or previous_outflow is None:
            return None

        max_ramp = float(max_ramp)
        previous_outflow = float(previous_outflow)
        min_allowed = previous_outflow - max_ramp
        max_allowed = previous_outflow + max_ramp
        clamped = max(min_allowed, min(max_allowed, outflow))
        if clamped == outflow:
            return None
        return {
            "action": "clamp_outflow",
            "min_outflow": min_allowed,
            "max_outflow": max_allowed,
            "reason": "ramp-rate limit",
        }
