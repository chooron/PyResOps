"""Constraint domain objects."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ConstraintScope = Literal["step", "global", "both"]
ConstraintSeverity = Literal["info", "warning", "minor", "major", "critical"]
ConstraintEnforcement = Literal["soft", "hard"]


class Constraint(BaseModel):
    """单个约束 (Single Constraint)."""

    id: str = Field(description="约束唯一标识")
    name: str = Field(description="约束名称")
    constraint_type: str = Field(description="约束类型 (如 'level_limit', 'flow_limit')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="约束参数")
    priority: int = Field(default=1, description="优先级 (数值越大越重要)")
    scope: ConstraintScope = Field(default="both", description="生效范围: 单步/全局/两者")
    severity: ConstraintSeverity = Field(default="major", description="严重等级")
    enforcement: ConstraintEnforcement = Field(default="hard", description="约束强度")
    enabled: bool = Field(default=True, description="是否启用")
    impl_class: str | None = Field(
        default=None,
        description="可选自定义实现类路径 (pkg.module:ClassName)",
    )
    tags: list[str] = Field(default_factory=list, description="扩展标签")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


class ConstraintSet(BaseModel):
    """约束集合 (Constraint Set)."""

    constraints: list[Constraint] = Field(default_factory=list)

    def add_constraint(self, constraint: Constraint) -> None:
        """添加约束."""
        self.constraints.append(constraint)

    def enabled_constraints(self) -> list[Constraint]:
        """返回启用的约束列表."""
        return [constraint for constraint in self.constraints if constraint.enabled]

    def get_by_type(self, constraint_type: str) -> list[Constraint]:
        """根据类型获取约束."""
        return [c for c in self.constraints if c.constraint_type == constraint_type]

    def get_by_scope(self, scope: Literal["step", "global"]) -> list[Constraint]:
        """按作用域获取约束."""
        return [
            constraint
            for constraint in self.enabled_constraints()
            if constraint.scope in (scope, "both")
        ]
