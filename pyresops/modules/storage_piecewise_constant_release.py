"""Piecewise-constant release as a function of storage."""

from __future__ import annotations

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule, ModuleOptimizationSpec


class StoragePiecewiseConstantReleaseModule(BaseOperationModule):
    """Piecewise-constant release rule driven by storage or storage ratio."""

    MODULE_TYPE = "storage_piecewise_constant_release"
    MODULE_NAME = "Storage Piecewise Constant Release"
    MODULE_DESCRIPTION = "Piecewise-constant release rule driven by storage bins."

    def validate_parameters(self) -> None:
        metric = str(self.parameters.get("metric", "storage_ratio"))
        if metric not in {"storage", "storage_ratio"}:
            raise ValueError("metric must be either 'storage' or 'storage_ratio'")

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
        self.parameters["metric"] = metric
        self.parameters["breakpoints"] = breakpoints
        self.parameters["release_values"] = release_values

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        metric_value = self._resolve_storage_metric(
            state=state,
            spec=spec,
            metric=self.parameters["metric"],
        )
        return self._select_piecewise_value(
            metric_value,
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
        flat_start = (initial_release, initial_release, initial_release)
        ramp_start = (
            min_release,
            cls._clip_value(initial_release, lower=min_release, upper=max_release),
            max_release,
        )
        return ModuleOptimizationSpec(
            solver_kind="local_continuous",
            bounds=((min_release, max_release), (min_release, max_release), (min_release, max_release)),
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
            "metric": "storage_ratio",
            "breakpoints": list(context["storage_piecewise_breakpoints"]),
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
                    "metric": {
                        "type": "string",
                        "enum": ["storage", "storage_ratio"],
                        "default": "storage_ratio",
                    },
                    "breakpoints": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Strictly increasing storage or storage-ratio breakpoints.",
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
