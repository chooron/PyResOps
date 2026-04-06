"""Constraint domain objects."""

from typing import Any

from pydantic import BaseModel, Field


class Constraint(BaseModel):
    """单个约束 (Single Constraint)."""

    id: str = Field(description="约束唯一标识")
    name: str = Field(description="约束名称")
    constraint_type: str = Field(description="约束类型 (如 'level_limit', 'flow_limit')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="约束参数")
    priority: int = Field(default=1, description="优先级 (数值越大越重要)")


class ConstraintSet(BaseModel):
    """约束集合 (Constraint Set)."""

    constraints: list[Constraint] = Field(default_factory=list)

    def add_constraint(self, constraint: Constraint) -> None:
        """添加约束."""
        self.constraints.append(constraint)

    def get_by_type(self, constraint_type: str) -> list[Constraint]:
        """根据类型获取约束."""
        return [c for c in self.constraints if c.constraint_type == constraint_type]
