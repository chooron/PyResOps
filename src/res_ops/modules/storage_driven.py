"""Storage-driven operation module."""

from typing import Any

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class StorageDrivenModule(BaseOperationModule):
    """蓄水量驱动模块 (Storage-Driven Module)."""

    MODULE_TYPE = "storage_driven"
    MODULE_NAME = "蓄水量驱动"
    MODULE_DESCRIPTION = "根据当前库容占比决定出库流量策略"

    def validate_parameters(self) -> None:
        """验证参数."""
        required = ["low_storage_threshold", "high_storage_threshold", "base_flow"]
        for param in required:
            if param not in self.parameters:
                raise ValueError(f"StorageDrivenModule requires '{param}' parameter")

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """
        计算出库流量.

        策略:
        - 库容低于 low_storage_threshold: 最小下泄 (base_flow)
        - 库容高于 high_storage_threshold: 加大下泄 (入流 + 额外释放)
        - 介于两者之间: 线性插值
        """
        storage_ratio = state.storage / spec.total_capacity

        low_threshold = self.parameters["low_storage_threshold"]
        high_threshold = self.parameters["high_storage_threshold"]
        base_flow = self.parameters["base_flow"]

        if storage_ratio < low_threshold:
            # 低水位: 最小下泄
            return base_flow
        elif storage_ratio > high_threshold:
            # 高水位: 加大下泄
            extra_release = self.parameters.get("extra_release_rate", 0.2) * spec.total_capacity * 1e8 / 3600  # 转换为 m³/s
            return inflow_forecast + extra_release
        else:
            # 中间水位: 线性插值
            ratio = (storage_ratio - low_threshold) / (high_threshold - low_threshold)
            return base_flow + ratio * (inflow_forecast - base_flow)

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
                    "low_storage_threshold": {
                        "type": "number",
                        "description": "低库容阈值 (占总库容比例)",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "high_storage_threshold": {
                        "type": "number",
                        "description": "高库容阈值 (占总库容比例)",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "base_flow": {
                        "type": "number",
                        "description": "基础流量 (m³/s)",
                        "minimum": 0,
                    },
                    "extra_release_rate": {
                        "type": "number",
                        "description": "高水位时额外释放率 (可选)",
                        "default": 0.2,
                        "minimum": 0,
                    },
                },
                "required": ["low_storage_threshold", "high_storage_threshold", "base_flow"],
            },
        )
