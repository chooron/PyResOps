"""External constraint response operation module."""

from typing import Any

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class ExternalConstraintModule(BaseOperationModule):
    """外部约束响应模块 (External Constraint Response Module)."""

    MODULE_TYPE = "external_constraint"
    MODULE_NAME = "外部约束响应"
    MODULE_DESCRIPTION = "根据下游断面控制流量等外部约束决定出库"

    def validate_parameters(self) -> None:
        """验证参数."""
        required = ["downstream_limit"]
        for param in required:
            if param not in self.parameters:
                raise ValueError(f"ExternalConstraintModule requires '{param}' parameter")

        self.parameters.setdefault("default_outflow", 5000.0)
        self.parameters.setdefault("safety_margin", 0.9)

        if self.parameters["downstream_limit"] < 0:
            raise ValueError("downstream_limit must be non-negative")
        if not 0 < self.parameters["safety_margin"] <= 1.0:
            raise ValueError("safety_margin must be in (0, 1]")

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """根据外部约束计算出流."""
        downstream_limit = self.parameters["downstream_limit"]
        safety_margin = self.parameters["safety_margin"]
        default_outflow = self.parameters["default_outflow"]

        # 安全约束上限
        safe_limit = downstream_limit * safety_margin

        # 默认策略: 在安全约束内尽量释放
        outflow = min(default_outflow, safe_limit)

        # 如果来水很大且远低于安全约束，可以适当增加泄量
        if inflow_forecast > safe_limit * 1.2:
            # 紧急情况: 按安全上限泄流
            outflow = safe_limit

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
                    "downstream_limit": {
                        "type": "number",
                        "description": "下游断面控制流量上限 (m³/s)",
                        "minimum": 0,
                    },
                    "default_outflow": {
                        "type": "number",
                        "description": "默认出库流量 (m³/s)",
                        "default": 5000.0,
                        "minimum": 0,
                    },
                    "safety_margin": {
                        "type": "number",
                        "description": "安全裕度系数 (0~1)",
                        "default": 0.9,
                        "minimum": 0,
                        "maximum": 1.0,
                    },
                },
                "required": ["downstream_limit"],
            },
        )
