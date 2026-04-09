"""Built-in level constraints."""

from __future__ import annotations

from ..base import ConstraintEvaluator


class LevelMaxConstraint(ConstraintEvaluator):
    """Maximum level constraint."""

    constraint_type = "level_max"

    def validate_global(self, *, result, context=None):
        max_level_limit = float(self.constraint.parameters.get("max_level", float("inf")))
        if result.max_level > max_level_limit:
            return [
                self._build_violation(
                    violation_type="level_exceeded",
                    scope="global",
                    value=result.max_level,
                    limit=max_level_limit,
                )
            ]
        return []

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        max_level_limit = float(self.constraint.parameters.get("max_level", float("inf")))
        if level > max_level_limit:
            return [
                self._build_violation(
                    violation_type="level_exceeded",
                    scope="step",
                    step_index=step_index,
                    value=level,
                    limit=max_level_limit,
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        max_level_limit = float(self.constraint.parameters.get("max_level", float("inf")))
        if level > max_level_limit:
            return {
                "action": "increase_outflow",
                "reason": "level exceeds max limit",
                "target_level": max_level_limit,
            }
        return None


class LevelMinConstraint(ConstraintEvaluator):
    """Minimum level constraint."""

    constraint_type = "level_min"

    def validate_global(self, *, result, context=None):
        min_level_limit = float(self.constraint.parameters.get("min_level", float("-inf")))
        if result.min_level < min_level_limit:
            return [
                self._build_violation(
                    violation_type="level_below",
                    scope="global",
                    value=result.min_level,
                    limit=min_level_limit,
                )
            ]
        return []

    def validate_step(self, *, step_index, level, inflow, outflow, context=None):
        min_level_limit = float(self.constraint.parameters.get("min_level", float("-inf")))
        if level < min_level_limit:
            return [
                self._build_violation(
                    violation_type="level_below",
                    scope="step",
                    step_index=step_index,
                    value=level,
                    limit=min_level_limit,
                )
            ]
        return []

    def suggest_adjustment(self, *, step_index, level, inflow, outflow, context=None):
        min_level_limit = float(self.constraint.parameters.get("min_level", float("-inf")))
        if level < min_level_limit:
            return {
                "action": "decrease_outflow",
                "reason": "level below min limit",
                "target_level": min_level_limit,
            }
        return None


class LevelRangeConstraint(ConstraintEvaluator):
    """Level range constraint."""

    constraint_type = "level_range"

    def validate_global(self, *, result, context=None):
        min_level = float(self.constraint.parameters.get("min_level", float("-inf")))
        max_level = float(self.constraint.parameters.get("max_level", float("inf")))
        if result.min_level < min_level or result.max_level > max_level:
            return [
                self._build_violation(
                    violation_type="level_range_violated",
                    scope="global",
                    details={
                        "min_value": result.min_level,
                        "max_value": result.max_level,
                        "min_limit": min_level,
                        "max_limit": max_level,
                    },
                )
            ]
        return []
