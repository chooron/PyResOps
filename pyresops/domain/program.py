"""Dispatch program domain objects."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TimeHorizon(BaseModel):
    """调度时段 (Time Horizon)."""

    start: datetime = Field(description="开始时间")
    end: datetime = Field(description="结束时间")
    time_step: int = Field(default=3600, description="时间步长 (秒)")

    def total_steps(self) -> int:
        """计算总步数."""
        duration = (self.end - self.start).total_seconds()
        return int(duration / self.time_step)


class ModuleInstance(BaseModel):
    """操作模块实例 (Operation Module Instance)."""

    module_type: str = Field(description="模块类型标识")
    parameters: dict[str, Any] = Field(default_factory=dict, description="模块参数")
    active_period: tuple[datetime, datetime] | None = Field(
        default=None, description="激活时段 (可选)"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class SwitchCondition(BaseModel):
    """模块切换条件 (Module Switch Condition)."""

    from_module: str = Field(description="源模块类型")
    to_module: str = Field(description="目标模块类型")
    condition_type: str = Field(description="条件类型 (如 'level_threshold', 'time_based')")
    parameters: dict[str, Any] = Field(default_factory=dict, description="条件参数")


class DispatchProgram(BaseModel):
    """调度方案 (Dispatch Program)."""

    id: str = Field(description="方案唯一标识")
    name: str = Field(description="方案名称")
    created_at: datetime = Field(default_factory=datetime.now)

    # 调度配置 (Dispatch Configuration)
    time_horizon: TimeHorizon = Field(description="调度时段")
    module_sequence: list[ModuleInstance] = Field(description="模块实例序列")
    switch_conditions: list[SwitchCondition] = Field(
        default_factory=list, description="切换条件列表"
    )

    # 元数据 (Metadata)
    metadata: dict[str, Any] = Field(default_factory=dict)
