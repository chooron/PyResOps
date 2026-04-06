"""Target level tracking operation module."""

from typing import Any

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class LevelTrackingModule(BaseOperationModule):
    """目标水位跟踪模块 (Target Level Tracking Module)."""

    MODULE_TYPE = "level_tracking"
    MODULE_NAME = "目标水位跟踪"
    MODULE_DESCRIPTION = "根据目标水位曲线调整出库流量，使水库水位跟踪目标"

    def validate_parameters(self) -> None:
        """验证参数."""
        required = ["target_level"]
        for param in required:
            if param not in self.parameters:
                raise ValueError(f"LevelTrackingModule requires '{param}' parameter")

        self.parameters.setdefault("kp", 500.0)
        self.parameters.setdefault("min_outflow", 0.0)
        self.parameters.setdefault("max_outflow", 999999.0)

        if self.parameters["kp"] <= 0:
            raise ValueError("kp (proportional gain) must be positive")

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """根据目标水位偏差计算出流."""
        target_level = self.parameters["target_level"]
        kp = self.parameters["kp"]
        min_outflow = self.parameters["min_outflow"]
        max_outflow = self.parameters["max_outflow"]

        # 水位偏差 (m): 正值表示水位高于目标
        level_error = state.level - target_level

        # 比例控制: 偏差大 -> 出流调整大
        # 正偏差 -> 增大出流降水位; 负偏差 -> 减小出流保水位
        outflow_adjustment = kp * level_error

        # 基于当前入流加调整量
        outflow = inflow_forecast + outflow_adjustment

        return max(min_outflow, min(max_outflow, outflow))

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
                    "target_level": {
                        "type": "number",
                        "description": "目标水位 (m)",
                    },
                    "kp": {
                        "type": "number",
                        "description": "比例增益 (m³/s per m of level error)",
                        "default": 500.0,
                        "minimum": 0,
                    },
                    "min_outflow": {
                        "type": "number",
                        "description": "最小出流限制 (m³/s)",
                        "default": 0.0,
                        "minimum": 0,
                    },
                    "max_outflow": {
                        "type": "number",
                        "description": "最大出流限制 (m³/s)",
                        "default": 999999.0,
                        "minimum": 0,
                    },
                },
                "required": ["target_level"],
            },
        )
