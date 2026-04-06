"""Base class for operation modules."""

from typing import Any

from ..domain.module import ModuleInfo, OperationModule
from ..domain.reservoir import ReservoirSpec, ReservoirState


class BaseOperationModule(OperationModule):
    """操作模块基类实现 (Base Operation Module Implementation)."""

    MODULE_TYPE: str = "base"
    MODULE_NAME: str = "Base Module"
    MODULE_DESCRIPTION: str = "Base operation module"

    def __init__(self, parameters: dict[str, Any]):
        """初始化模块."""
        super().__init__(parameters)
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """验证参数合法性."""
        pass

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """计算出库流量 (默认实现: 入流等于出流)."""
        return inflow_forecast

    @classmethod
    def get_info(cls) -> ModuleInfo:
        """获取模块元信息."""
        return ModuleInfo(
            module_type=cls.MODULE_TYPE,
            name=cls.MODULE_NAME,
            description=cls.MODULE_DESCRIPTION,
            parameters_schema={},
        )
