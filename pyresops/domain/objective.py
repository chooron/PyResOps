"""Objective domain objects."""

from typing import Any

from pydantic import BaseModel, Field


class Objective(BaseModel):
    """单个目标 (Single Objective)."""

    id: str = Field(description="目标唯一标识")
    name: str = Field(description="目标名称")
    objective_type: str = Field(
        description="目标类型 (如 'minimize_flood_risk', 'maximize_power')"
    )
    parameters: dict[str, Any] = Field(default_factory=dict, description="目标参数")
    weight: float = Field(default=1.0, description="权重")


class ObjectiveSet(BaseModel):
    """目标集合 (Objective Set)."""

    objectives: list[Objective] = Field(default_factory=list)

    def add_objective(self, objective: Objective) -> None:
        """添加目标."""
        self.objectives.append(objective)

    def get_by_type(self, objective_type: str) -> list[Objective]:
        """根据类型获取目标."""
        return [o for o in self.objectives if o.objective_type == objective_type]
