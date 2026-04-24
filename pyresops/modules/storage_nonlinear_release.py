"""Continuous or piecewise-linear release as a function of storage."""

from __future__ import annotations

import numpy as np

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule, ModuleOptimizationSpec


class StorageNonlinearReleaseModule(BaseOperationModule):
    """Continuous release mapping driven by storage or storage ratio."""

    MODULE_TYPE = "storage_nonlinear_release"
    MODULE_NAME = "Storage Nonlinear Release"
    MODULE_DESCRIPTION = "Continuous or piecewise-linear release rule driven by storage."

    def validate_parameters(self) -> None:
        metric = str(self.parameters.get("metric", "storage_ratio"))
        if metric not in {"storage", "storage_ratio"}:
            raise ValueError("metric must be either 'storage' or 'storage_ratio'")

        control_points = self._coerce_float_list(
            "control_points", self.parameters.get("control_points", [])
        )
        release_values = self._coerce_float_list(
            "release_values", self.parameters.get("release_values", [])
        )
        if len(control_points) != len(release_values):
            raise ValueError("release_values must have the same length as control_points")
        self._validate_strictly_increasing("control_points", control_points)
        for release in release_values:
            self._require_non_negative("release_values", release)
        self.parameters["metric"] = metric
        self.parameters["control_points"] = control_points
        self.parameters["release_values"] = release_values

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        metric_value = self._resolve_storage_metric(
            state=state,
            spec=spec,
            metric=self.parameters["metric"],
        )
        return float(
            np.interp(
                float(metric_value),
                self.parameters["control_points"],
                self.parameters["release_values"],
            )
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
        flat_start = (initial_release, initial_release, initial_release, initial_release)
        ramp_start = (
            min_release,
            cls._clip_value(initial_release, lower=min_release, upper=max_release),
            cls._clip_value(initial_release + 0.15 * (max_release - min_release), lower=min_release, upper=max_release),
            max_release,
        )
        return ModuleOptimizationSpec(
            solver_kind="local_continuous",
            bounds=tuple((min_release, max_release) for _ in range(4)),
            initial_guesses=(flat_start, ramp_start),
            max_iterations=160,
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
            "control_points": list(context["storage_nonlinear_control_points"]),
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
                    "control_points": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Strictly increasing storage or storage-ratio control points.",
                    },
                    "release_values": {
                        "type": "array",
                        "items": {"type": "number", "minimum": 0},
                        "description": "Release values aligned with control_points.",
                    },
                },
                "required": ["control_points", "release_values"],
            },
        )
