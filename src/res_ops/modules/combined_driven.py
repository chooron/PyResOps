"""Combined-driven operation module (joint inflow + storage)."""

from typing import Any

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class CombinedDrivenModule(BaseOperationModule):
    """联合驱动模块 (Combined Inflow + Storage Driven Module)."""

    MODULE_TYPE = "combined_driven"
    MODULE_NAME = "联合驱动"
    MODULE_DESCRIPTION = "综合考虑入库流量和当前库容决定出库流量"

    def validate_parameters(self) -> None:
        """验证参数."""
        self.parameters.setdefault("inflow_weight", 0.5)
        self.parameters.setdefault("storage_weight", 0.5)
        self.parameters.setdefault("base_flow", 5000.0)
        self.parameters.setdefault("low_storage_threshold", 0.3)
        self.parameters.setdefault("high_storage_threshold", 0.8)

        w_in = self.parameters["inflow_weight"]
        w_st = self.parameters["storage_weight"]
        if w_in < 0 or w_st < 0:
            raise ValueError("weights must be non-negative")
        if w_in + w_st == 0:
            raise ValueError("at least one weight must be positive")

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """综合入流与库容计算出流."""
        w_in = self.parameters["inflow_weight"]
        w_st = self.parameters["storage_weight"]
        base_flow = self.parameters["base_flow"]
        low_th = self.parameters["low_storage_threshold"]
        high_th = self.parameters["high_storage_threshold"]

        # 入流分量: 出流跟随入流
        inflow_component = inflow_forecast

        # 库容分量: 按库容比例调整
        storage_ratio = state.storage / spec.total_capacity
        if storage_ratio < low_th:
            storage_component = base_flow * 0.5
        elif storage_ratio > high_th:
            storage_component = base_flow * 2.0
        else:
            ratio = (storage_ratio - low_th) / (high_th - low_th)
            storage_component = base_flow * (0.5 + 1.5 * ratio)

        # 加权组合
        total_weight = w_in + w_st
        outflow = (w_in * inflow_component + w_st * storage_component) / total_weight

        return max(0.0, outflow)

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
                    "inflow_weight": {
                        "type": "number",
                        "description": "入流分量权重",
                        "default": 0.5,
                        "minimum": 0,
                    },
                    "storage_weight": {
                        "type": "number",
                        "description": "库容分量权重",
                        "default": 0.5,
                        "minimum": 0,
                    },
                    "base_flow": {
                        "type": "number",
                        "description": "基础流量 (m³/s)",
                        "default": 5000.0,
                        "minimum": 0,
                    },
                    "low_storage_threshold": {
                        "type": "number",
                        "description": "低库容阈值 (占总库容比例)",
                        "default": 0.3,
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "high_storage_threshold": {
                        "type": "number",
                        "description": "高库容阈值 (占总库容比例)",
                        "default": 0.8,
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
            },
        )
