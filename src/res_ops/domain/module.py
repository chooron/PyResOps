"""Operation module base class and metadata."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from .reservoir import ReservoirSpec, ReservoirState


class ModuleInfo(BaseModel):
    """操作模块元信息 (Operation Module Info)."""

    module_type: str = Field(description="模块类型标识")
    name: str = Field(description="模块名称")
    description: str = Field(description="模块描述")
    parameters_schema: dict[str, Any] = Field(description="参数 schema")


class OperationModule(ABC):
    """操作模块基类 (Operation Module Base Class)."""

    def __init__(self, parameters: dict[str, Any]):
        """初始化模块."""
        self.parameters = parameters

    @abstractmethod
    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """
        计算出库流量.

        Args:
            state: 当前水库状态
            spec: 水库规范参数
            inflow_forecast: 预报入库流量

        Returns:
            计算的出库流量 (m³/s)
        """
        pass

    @classmethod
    @abstractmethod
    def get_info(cls) -> ModuleInfo:
        """获取模块元信息."""
        pass
