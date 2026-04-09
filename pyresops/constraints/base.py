"""Constraint evaluator protocol and base implementation."""

from __future__ import annotations

from abc import ABC
from typing import Any

from ..domain.constraint import Constraint
from ..domain.decision import ViolationRecord
from ..domain.result import SimulationResult


class ConstraintEvaluator(ABC):
    """Pluggable evaluator for one constraint type.

    Minimal custom evaluator template:

    ```python
    from pyresops.constraints.base import ConstraintEvaluator


    class MyConstraint(ConstraintEvaluator):
        constraint_type = "my_constraint"

        def validate_step(self, *, step_index, level, inflow, outflow, context=None):
            limit = float(self.constraint.parameters.get("limit", 0.0))
            if outflow > limit:
                return [
                    self._build_violation(
                        violation_type="flow_exceeded",
                        scope="step",
                        step_index=step_index,
                        value=outflow,
                        limit=limit,
                    )
                ]
            return []
    ```
    """

    constraint_type: str = "base"

    def __init__(self, constraint: Constraint):
        self.constraint = constraint

    def validate_global(
        self,
        *,
        result: SimulationResult,
        context: dict[str, Any] | None = None,
    ) -> list[ViolationRecord]:
        """Validate global-result constraints."""
        return []

    def validate_step(
        self,
        *,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
        context: dict[str, Any] | None = None,
    ) -> list[ViolationRecord]:
        """Validate step constraints."""
        return []

    def suggest_adjustment(
        self,
        *,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Optional adjustment hints when violation occurs."""
        return None

    def _build_violation(
        self,
        *,
        violation_type: str,
        scope: str,
        step_index: int | None = None,
        value: float | None = None,
        limit: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> ViolationRecord:
        """Build a normalized violation record."""
        return ViolationRecord(
            constraint_id=self.constraint.id,
            constraint_name=self.constraint.name,
            violation_type=violation_type,
            severity=self.constraint.severity,
            enforcement=self.constraint.enforcement,
            scope=scope,
            step_index=step_index,
            value=value,
            limit=limit,
            details=details or {},
        )
