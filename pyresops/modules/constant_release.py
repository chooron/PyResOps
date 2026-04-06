"""Constant release operation module."""

from typing import Any

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class ConstantReleaseModule(BaseOperationModule):
    """恒定下泄模块 (Constant Release Module)."""

    MODULE_TYPE = "constant_release"
    MODULE_NAME = "恒定下泄"
    MODULE_DESCRIPTION = "维持固定的出库流量"

    def validate_parameters(self) -> None:
        """验证参数."""
        if "target_flow" not in self.parameters:
            raise ValueError("ConstantReleaseModule requires 'target_flow' parameter")

        if self.parameters["target_flow"] < 0:
            raise ValueError("target_flow must be non-negative")

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """计算出库流量: 返回固定流量."""
        return float(self.parameters["target_flow"])

    @classmethod
    def get_info(cls) -> ModuleInfo:
        """获取模块元信息."""
        return ModuleInfo(
            module_type=cls.MODULE_TYPE,
            name=cls.MODULE_NAME,
            description=cls.MODULE_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_flow": {
                        "type": "number",
                        "description": "目标出库流量 (m³/s)",
                        "minimum": 0,
                    }
                },
                "required": ["target_flow"],
            },
        )
