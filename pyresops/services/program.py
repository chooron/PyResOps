"""Program service for dispatch program management."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from ..domain.program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from ..modules import (
    BASE_RELEASE_MODULE_REGISTRY,
    assert_supported_base_release_module_type,
)


class ProgramService:
    """Manage dispatch programs built from paper-aligned base release modules."""

    def __init__(self):
        self._programs: dict[str, DispatchProgram] = {}
        self._module_registry = dict(BASE_RELEASE_MODULE_REGISTRY)

    def create_program(
        self,
        name: str,
        time_horizon: TimeHorizon,
        module_configs: list[dict[str, Any]],
        switch_conditions: list[SwitchCondition] | None = None,
        metadata: dict[str, Any] | None = None,
        program_id: str | None = None,
    ) -> DispatchProgram:
        module_sequence: list[ModuleInstance] = []
        for cfg in module_configs:
            module_type = str(cfg["module_type"])
            assert_supported_base_release_module_type(module_type)
            module_sequence.append(
                ModuleInstance(
                    module_type=module_type,
                    parameters=cfg.get("parameters", {}),
                    active_period=cfg.get("active_period"),
                    metadata=cfg.get("metadata", {}),
                )
            )

        resolved_switch_conditions = switch_conditions or []
        for condition in resolved_switch_conditions:
            assert_supported_base_release_module_type(condition.from_module)
            assert_supported_base_release_module_type(condition.to_module)

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
        for module in program.module_sequence:
            assert_supported_base_release_module_type(module.module_type)
        for condition in program.switch_conditions:
            assert_supported_base_release_module_type(condition.from_module)
            assert_supported_base_release_module_type(condition.to_module)

    def get_program(self, program_id: str) -> DispatchProgram | None:
        return self._programs.get(program_id)

    def list_programs(self) -> list[DispatchProgram]:
        return list(self._programs.values())

    def list_available_modules(self) -> list[dict[str, Any]]:
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
        return dict(self._module_registry)
