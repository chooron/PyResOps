"""Constraint validation for simulation results."""

from __future__ import annotations

from typing import Any

from ..constraints import (
    ConstraintFactory,
    ConstraintRegistry,
    register_builtin_constraints,
)
from ..domain.constraint import ConstraintSet
from ..domain.decision import ViolationRecord
from ..domain.result import SimulationResult


class ConstraintValidator:
    """约束校核器 (Constraint Validator)."""

    def __init__(
        self,
        constraint_set: ConstraintSet,
        registry: ConstraintRegistry | None = None,
    ):
        """初始化校核器."""
        self.constraint_set = constraint_set
        self.registry = registry or ConstraintRegistry()
        register_builtin_constraints(self.registry)
        self.factory = ConstraintFactory(self.registry)

    def validate_simulation(self, result: SimulationResult) -> list[dict[str, Any]]:
        """
        校核仿真结果是否满足约束.

        Args:
            result: 仿真结果

        Returns:
            约束违反记录列表
        """
        violations: list[ViolationRecord] = []
        for constraint in self.constraint_set.get_by_scope("global"):
            evaluator = self.factory.create(constraint)
            if evaluator is None:
                continue
            violations.extend(evaluator.validate_global(result=result))

        return [item.to_legacy_dict() for item in violations]

    def validate_step(
        self,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
        previous_outflow: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        校核单步状态是否满足约束.

        Args:
            step_index: 步序号
            level: 当前水位 (m)
            inflow: 入库流量 (m³/s)
            outflow: 出库流量 (m³/s)

        Returns:
            约束违反记录列表
        """
        violations: list[ViolationRecord] = []
        for constraint in self.constraint_set.get_by_scope("step"):
            evaluator = self.factory.create(constraint)
            if evaluator is None:
                continue

            violations.extend(
                evaluator.validate_step(
                    step_index=step_index,
                    level=level,
                    inflow=inflow,
                    outflow=outflow,
                    context={"previous_outflow": previous_outflow},
                )
            )

        return [item.to_legacy_dict() for item in violations]
