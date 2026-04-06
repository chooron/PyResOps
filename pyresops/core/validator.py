"""Constraint validation for simulation results."""

from typing import Any

from ..domain.constraint import Constraint, ConstraintSet
from ..domain.result import SimulationResult


class ConstraintValidator:
    """约束校核器 (Constraint Validator)."""

    def __init__(self, constraint_set: ConstraintSet):
        """初始化校核器."""
        self.constraint_set = constraint_set

    def validate_simulation(self, result: SimulationResult) -> list[dict[str, Any]]:
        """
        校核仿真结果是否满足约束.

        Args:
            result: 仿真结果

        Returns:
            约束违反记录列表
        """
        violations: list[dict[str, Any]] = []

        for constraint in self.constraint_set.constraints:
            violation = self._check_constraint(constraint, result)
            if violation:
                violations.append(violation)

        return violations

    def validate_step(
        self,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
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
        violations: list[dict[str, Any]] = []

        for constraint in self.constraint_set.constraints:
            violation = self._check_step_constraint(constraint, step_index, level, inflow, outflow)
            if violation:
                violations.append(violation)

        return violations

    def _check_constraint(
        self, constraint: Constraint, result: SimulationResult
    ) -> dict[str, Any] | None:
        """检查单个约束 (全局)."""
        ctype = constraint.constraint_type

        if ctype == "level_max":
            max_level_limit = constraint.parameters.get("max_level", float("inf"))
            if result.max_level > max_level_limit:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "violation_type": "level_exceeded",
                    "value": result.max_level,
                    "limit": max_level_limit,
                }

        elif ctype == "level_min":
            min_level_limit = constraint.parameters.get("min_level", float("-inf"))
            if result.min_level < min_level_limit:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "violation_type": "level_below",
                    "value": result.min_level,
                    "limit": min_level_limit,
                }

        elif ctype == "flow_max":
            max_flow_limit = constraint.parameters.get("max_flow", float("inf"))
            if result.snapshots:
                max_outflow = max(s.outflow for s in result.snapshots)
                if max_outflow > max_flow_limit:
                    return {
                        "constraint_id": constraint.id,
                        "constraint_name": constraint.name,
                        "violation_type": "flow_exceeded",
                        "value": max_outflow,
                        "limit": max_flow_limit,
                    }

        elif ctype == "flow_min":
            min_flow_limit = constraint.parameters.get("min_flow", float("-inf"))
            if result.snapshots:
                min_outflow = min(s.outflow for s in result.snapshots)
                if min_outflow < min_flow_limit:
                    return {
                        "constraint_id": constraint.id,
                        "constraint_name": constraint.name,
                        "violation_type": "flow_below",
                        "value": min_outflow,
                        "limit": min_flow_limit,
                    }

        elif ctype == "water_supply":
            # 供水约束: 全程平均出流不应低于需求
            demand = constraint.parameters.get("demand", 0.0)
            if result.avg_outflow < demand:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "violation_type": "water_supply_insufficient",
                    "value": result.avg_outflow,
                    "limit": demand,
                }

        elif ctype == "level_range":
            min_level = constraint.parameters.get("min_level", float("-inf"))
            max_level = constraint.parameters.get("max_level", float("inf"))
            if result.min_level < min_level or result.max_level > max_level:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "violation_type": "level_range_violated",
                    "min_value": result.min_level,
                    "max_value": result.max_level,
                    "min_limit": min_level,
                    "max_limit": max_level,
                }

        return None

    def _check_step_constraint(
        self,
        constraint: Constraint,
        step_index: int,
        level: float,
        inflow: float,
        outflow: float,
    ) -> dict[str, Any] | None:
        """检查单步约束."""
        ctype = constraint.constraint_type

        if ctype == "level_max":
            max_level_limit = constraint.parameters.get("max_level", float("inf"))
            if level > max_level_limit:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "step_index": step_index,
                    "violation_type": "level_exceeded",
                    "value": level,
                    "limit": max_level_limit,
                }

        elif ctype == "level_min":
            min_level_limit = constraint.parameters.get("min_level", float("-inf"))
            if level < min_level_limit:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "step_index": step_index,
                    "violation_type": "level_below",
                    "value": level,
                    "limit": min_level_limit,
                }

        elif ctype == "flow_max":
            max_flow_limit = constraint.parameters.get("max_flow", float("inf"))
            if outflow > max_flow_limit:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "step_index": step_index,
                    "violation_type": "flow_exceeded",
                    "value": outflow,
                    "limit": max_flow_limit,
                }

        elif ctype == "flow_min":
            min_flow_limit = constraint.parameters.get("min_flow", float("-inf"))
            if outflow < min_flow_limit:
                return {
                    "constraint_id": constraint.id,
                    "constraint_name": constraint.name,
                    "step_index": step_index,
                    "violation_type": "flow_below",
                    "value": outflow,
                    "limit": min_flow_limit,
                }

        return None
