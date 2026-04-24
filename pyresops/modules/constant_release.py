"""Constant release operation module."""

from __future__ import annotations

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule, ModuleOptimizationSpec


class ConstantReleaseModule(BaseOperationModule):
    """Fixed release rule."""

    MODULE_TYPE = "constant_release"
    MODULE_NAME = "Constant Release"
    MODULE_DESCRIPTION = "Fixed release rule with a single target release."

    def validate_parameters(self) -> None:
        target_release = self.parameters.get("target_release", self.parameters.get("target_flow"))
        if target_release is None:
            raise ValueError("ConstantReleaseModule requires 'target_release'")
        self._require_non_negative("target_release", float(target_release))
        self.parameters["target_release"] = float(target_release)

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        return float(self.parameters["target_release"])

    @classmethod
    def get_optimization_spec(cls, *, context: dict[str, float]) -> ModuleOptimizationSpec:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        initial_release = cls._clip_value(
            float(context["initial_release_guess"]),
            lower=min_release,
            upper=max_release,
        )
        return ModuleOptimizationSpec(
            solver_kind="bounded_scalar",
            bounds=((min_release, max_release),),
            initial_guesses=((initial_release,),),
            max_iterations=80,
        )

    @classmethod
    def decode_optimization_vector(
        cls,
        vector,
        *,
        context: dict[str, float],
    ) -> dict[str, float]:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        value = float(vector[0] if isinstance(vector, (list, tuple)) else vector)
        return {
            "target_release": cls._clip_value(
                value,
                lower=min_release,
                upper=max_release,
            )
        }

    @classmethod
    def get_info(cls) -> ModuleInfo:
        return ModuleInfo(
            module_type=cls.MODULE_TYPE,
            name=cls.MODULE_NAME,
            description=cls.MODULE_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_release": {
                        "type": "number",
                        "description": "Fixed release value.",
                        "minimum": 0,
                    }
                },
                "required": ["target_release"],
            },
        )
