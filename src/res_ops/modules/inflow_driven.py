"""Inflow-driven operation module."""

from typing import Any

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class InflowDrivenModule(BaseOperationModule):
    """入流驱动模块 (Inflow-Driven Module)."""

    MODULE_TYPE = "inflow_driven"
    MODULE_NAME = "入流驱动"
    MODULE_DESCRIPTION = "出库流量跟随入库流量变化，可设置系数调整"

    def validate_parameters(self) -> None:
        """验证参数."""
        self.parameters.setdefault("coefficient", 1.0)

        if self.parameters["coefficient"] < 0:
            raise ValueError("coefficient must be non-negative")

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """计算出库流量: 出流 = 系数 * 入流."""
        coefficient = self.parameters["coefficient"]
        return coefficient * inflow_forecast

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
                    "coefficient": {
                        "type": "number",
                        "description": "入流系数 (默认1.0，出流=入流)",
                        "default": 1.0,
                        "minimum": 0,
                    }
                },
            },
        )
