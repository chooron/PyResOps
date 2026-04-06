"""Program service for dispatch program management."""

from datetime import datetime
from typing import Any

from ..domain.program import DispatchProgram, ModuleInstance, TimeHorizon
from ..modules import (
    CombinedDrivenModule,
    ConstantReleaseModule,
    ExternalConstraintModule,
    InflowDrivenModule,
    LevelTrackingModule,
    StorageDrivenModule,
)


class ProgramService:
    """方案服务 (Program Service)."""

    def __init__(self):
        """初始化方案服务."""
        self._programs: dict[str, DispatchProgram] = {}
        self._module_registry = {
            "constant_release": ConstantReleaseModule,
            "inflow_driven": InflowDrivenModule,
            "storage_driven": StorageDrivenModule,
            "combined_driven": CombinedDrivenModule,
            "level_tracking": LevelTrackingModule,
            "external_constraint": ExternalConstraintModule,
        }

    def create_program(
        self,
        name: str,
        time_horizon: TimeHorizon,
        module_configs: list[dict[str, Any]],
    ) -> DispatchProgram:
        """
        创建调度方案.

        Args:
            name: 方案名称
            time_horizon: 调度时段
            module_configs: 模块配置列表

        Returns:
            创建的调度方案
        """
        module_sequence = [
            ModuleInstance(
                module_type=cfg["module_type"],
                parameters=cfg.get("parameters", {}),
                active_period=cfg.get("active_period"),
            )
            for cfg in module_configs
        ]

        program = DispatchProgram(
            id=f"prog_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            name=name,
            time_horizon=time_horizon,
            module_sequence=module_sequence,
        )

        self._programs[program.id] = program
        return program

    def get_program(self, program_id: str) -> DispatchProgram | None:
        """获取调度方案."""
        return self._programs.get(program_id)

    def list_programs(self) -> list[DispatchProgram]:
        """列出所有方案."""
        return list(self._programs.values())

    def list_available_modules(self) -> list[dict[str, Any]]:
        """列出可用的操作模块."""
        modules = []
        for module_type, module_class in self._module_registry.items():
            info = module_class.get_info()
            modules.append(
                {
                    "module_type": info.module_type,
                    "name": info.name,
                    "description": info.description,
                    "parameters_schema": info.parameters_schema,
                }
            )
        return modules

    def get_module_registry(self) -> dict[str, type]:
        """获取模块注册表."""
        return self._module_registry
