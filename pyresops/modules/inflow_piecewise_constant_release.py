"""Piecewise-constant release as a function of inflow."""

from __future__ import annotations

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule, ModuleOptimizationSpec


class InflowPiecewiseConstantReleaseModule(BaseOperationModule):
    """Qout = f(Qin) with piecewise-constant feedback."""

    MODULE_TYPE = "inflow_piecewise_constant_release"
    MODULE_NAME = "Inflow Piecewise Constant Release"
    MODULE_DESCRIPTION = "Piecewise-constant release rule driven by inflow bins."

    def validate_parameters(self) -> None:
        breakpoints = self._coerce_float_list(
            "breakpoints", self.parameters.get("breakpoints", [])
        )
        release_values = self._coerce_float_list(
            "release_values", self.parameters.get("release_values", [])
        )
        self._validate_piecewise_shape(
            breakpoints=breakpoints,
            release_values=release_values,
            breakpoint_name="breakpoints",
            release_name="release_values",
        )
        self.parameters["breakpoints"] = breakpoints
        self.parameters["release_values"] = release_values

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        return self._select_piecewise_value(
            inflow_forecast,
            self.parameters["breakpoints"],
            self.parameters["release_values"],
        )

    @classmethod
    def get_optimization_spec(cls, *, context: dict[str, float]) -> ModuleOptimizationSpec:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        initial_release = cls._clip_value(
            float(context["initial_release_guess"]),
            lower=min_release,
            upper=max_release,
        )
        breakpoint_count = len(context["inflow_breakpoints"])
        release_dimension = breakpoint_count + 1
        flat_start = tuple(initial_release for _ in range(release_dimension))
        ramp_start = tuple(
            min_release + (max_release - min_release) * index / max(release_dimension - 1, 1)
            for index in range(release_dimension)
        )
        return ModuleOptimizationSpec(
            solver_kind="local_continuous",
            bounds=tuple((min_release, max_release) for _ in range(release_dimension)),
            initial_guesses=(flat_start, ramp_start),
            max_iterations=140,
        )

    @classmethod
    def decode_optimization_vector(
        cls,
        vector,
        *,
        context: dict[str, float],
    ) -> dict[str, object]:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        release_values = cls._project_monotone_release_values(
            vector,
            lower=min_release,
            upper=max_release,
        )
        return {
            "breakpoints": list(context["inflow_breakpoints"]),
            "release_values": [round(float(value), 6) for value in release_values],
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
                    "breakpoints": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Strictly increasing inflow breakpoints.",
                    },
                    "release_values": {
                        "type": "array",
                        "items": {"type": "number", "minimum": 0},
                        "description": "Bin releases with len = len(breakpoints) + 1.",
                    },
                },
                "required": ["breakpoints", "release_values"],
            },
        )
