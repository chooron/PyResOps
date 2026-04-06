"""Reservoir domain objects: specifications and states."""

from datetime import datetime
from typing import Any

import numpy as np
from pydantic import BaseModel, Field, field_validator


class LevelStorageCurve(BaseModel):
    """水位-库容关系曲线 (Level-Storage Curve)."""

    levels: list[float] = Field(description="水位序列 (m)")
    storages: list[float] = Field(description="库容序列 (亿m³)")

    @field_validator("levels", "storages")
    @classmethod
    def check_ascending(cls, v: list[float]) -> list[float]:
        """Ensure values are in ascending order."""
        if not all(v[i] < v[i + 1] for i in range(len(v) - 1)):
            raise ValueError("Values must be strictly ascending")
        return v

    def get_storage(self, level: float) -> float:
        """根据水位插值计算库容."""
        return float(np.interp(level, self.levels, self.storages))

    def get_level(self, storage: float) -> float:
        """根据库容插值计算水位."""
        return float(np.interp(storage, self.storages, self.levels))


class DischargeCapacity(BaseModel):
    """泄流能力曲线 (Discharge Capacity Curve)."""

    levels: list[float] = Field(description="水位序列 (m)")
    max_discharges: list[float] = Field(description="最大泄流能力 (m³/s)")

    @field_validator("levels", "max_discharges")
    @classmethod
    def check_ascending_levels(cls, v: list[float]) -> list[float]:
        """Ensure levels are in ascending order."""
        if not all(v[i] < v[i + 1] for i in range(len(v) - 1)):
            raise ValueError("Levels must be strictly ascending")
        return v

    def get_max_discharge(self, level: float) -> float:
        """根据水位插值计算最大泄流能力."""
        return float(np.interp(level, self.levels, self.max_discharges))


class ReservoirSpec(BaseModel):
    """水库静态参数规范 (Reservoir Specification)."""

    id: str = Field(description="水库唯一标识")
    name: str = Field(description="水库名称")

    # 特征水位 (Characteristic Levels)
    dead_level: float = Field(description="死水位 (m)")
    normal_level: float = Field(description="正常蓄水位 (m)")
    flood_limit_level: float = Field(description="汛限水位 (m)")
    design_flood_level: float = Field(description="设计洪水位 (m)")
    check_flood_level: float = Field(description="校核洪水位 (m)")

    # 库容特性 (Capacity Characteristics)
    total_capacity: float = Field(description="总库容 (亿m³)")
    flood_capacity: float = Field(description="防洪库容 (亿m³)")

    # 水力特性曲线 (Hydraulic Curves)
    level_storage_curve: LevelStorageCurve = Field(description="水位-库容曲线")
    discharge_capacity: DischargeCapacity = Field(description="泄流能力曲线")

    # 元数据 (Metadata)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def validate_level_range(self, level: float) -> bool:
        """检查水位是否在合理范围内."""
        return self.dead_level <= level <= self.check_flood_level


class ReservoirState(BaseModel):
    """水库实时状态 (Reservoir State)."""

    timestamp: datetime = Field(description="状态时间戳")
    level: float = Field(description="当前水位 (m)")
    storage: float = Field(description="当前库容 (亿m³)")
    inflow: float = Field(description="当前入库流量 (m³/s)")
    outflow: float = Field(description="当前出库流量 (m³/s)")

    # 运行信息 (Operation Info)
    active_module_id: str | None = Field(default=None, description="当前激活的操作模块ID")
    metadata: dict[str, Any] = Field(default_factory=dict)

    def copy_with_update(self, **kwargs: Any) -> "ReservoirState":
        """创建更新后的状态副本."""
        data = self.model_dump()
        data.update(kwargs)
        return ReservoirState(**data)
