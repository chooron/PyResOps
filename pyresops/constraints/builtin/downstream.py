"""Built-in downstream section constraints."""

from __future__ import annotations

from ..base import ConstraintEvaluator


class DownstreamFlowLimitConstraint(ConstraintEvaluator):
    """Generic downstream section flow cap."""

    constraint_type = "downstream_flow_limit"

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        section_limit = self.constraint.parameters.get("max_section_flow")
        if section_limit is None:
            return []
        section_limit = float(section_limit)

        lagged_component = 0.0
        if context:
            lagged_component = float(context.get("downstream_lagged_flow", 0.0))

        section_flow = outflow + lagged_component
        if section_flow > section_limit:
            return [
                self._build_violation(
                    violation_type="downstream_section_exceeded",
                    scope="step",
                    step_index=step_index,
                    value=section_flow,
                    limit=section_limit,
                    details={"lagged_component": lagged_component},
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        section_limit = self.constraint.parameters.get("max_section_flow")
        if section_limit is None:
            return None
        section_limit = float(section_limit)
        lagged_component = float((context or {}).get("downstream_lagged_flow", 0.0))
        allowed_outflow = section_limit - lagged_component
        if outflow <= allowed_outflow:
            return None
        return {
            "action": "clamp_outflow",
            "max_outflow": max(0.0, allowed_outflow),
            "reason": "downstream section flow limit",
        }
