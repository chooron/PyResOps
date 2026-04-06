"""Program service for dispatch program management."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from ..domain.program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from ..modules import (
    CombinedDrivenModule,
    ConstantReleaseModule,
    ExternalConstraintModule,
    FlexibleReleaseModule,
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
            "flexible_release": FlexibleReleaseModule,
        }

    def create_program(
        self,
        name: str,
        time_horizon: TimeHorizon,
        module_configs: list[dict[str, Any]],
        switch_conditions: list[SwitchCondition] | None = None,
        metadata: dict[str, Any] | None = None,
        program_id: str | None = None,
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

        resolved_switch_conditions = switch_conditions or []
        program = DispatchProgram(
            id=program_id or f"prog_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}",
            name=name,
            time_horizon=time_horizon,
            module_sequence=module_sequence,
            switch_conditions=resolved_switch_conditions,
            metadata=metadata or {},
        )
        self.validate_program(program)

        self._programs[program.id] = program
        return program

    def validate_program(self, program: DispatchProgram) -> None:
        """Validate program-level invariants for V1."""
        flexible_modules = [
            module for module in program.module_sequence if module.module_type == "flexible_release"
        ]
        if len(flexible_modules) > 1:
            raise ValueError("V1 supports at most one flexible_release module per program")

        if flexible_modules and program.switch_conditions:
            raise ValueError("V1 does not allow mixing flexible_release with switch_conditions")

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
