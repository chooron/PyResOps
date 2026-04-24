"""Joint inflow-storage release rule."""

from __future__ import annotations

from bisect import bisect_right

from ..domain.module import ModuleInfo
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule, ModuleOptimizationSpec


class JointDrivenReleaseModule(BaseOperationModule):
    """Two-dimensional joint release rule driven by inflow and storage."""

    MODULE_TYPE = "joint_driven_release"
    MODULE_NAME = "Joint Driven Release"
    MODULE_DESCRIPTION = "Joint release rule driven by inflow and storage together."

    def validate_parameters(self) -> None:
        storage_metric = str(self.parameters.get("storage_metric", "storage_ratio"))
        if storage_metric not in {"storage", "storage_ratio"}:
            raise ValueError("storage_metric must be either 'storage' or 'storage_ratio'")

        inflow_breakpoints = [
            float(value) for value in self.parameters.get("inflow_breakpoints", [])
        ]
        storage_breakpoints = [
            float(value) for value in self.parameters.get("storage_breakpoints", [])
        ]
        release_matrix = [
            [float(cell) for cell in row]
            for row in self.parameters.get("release_matrix", [])
        ]

        self._validate_strictly_increasing("inflow_breakpoints", inflow_breakpoints)
        self._validate_strictly_increasing("storage_breakpoints", storage_breakpoints)

        expected_rows = len(inflow_breakpoints) + 1
        expected_cols = len(storage_breakpoints) + 1
        if len(release_matrix) != expected_rows:
            raise ValueError("release_matrix row count must equal len(inflow_breakpoints) + 1")
        for row in release_matrix:
            if len(row) != expected_cols:
                raise ValueError(
                    "release_matrix column count must equal len(storage_breakpoints) + 1"
                )
            for value in row:
                self._require_non_negative("release_matrix", value)

        self.parameters["storage_metric"] = storage_metric
        self.parameters["inflow_breakpoints"] = inflow_breakpoints
        self.parameters["storage_breakpoints"] = storage_breakpoints
        self.parameters["release_matrix"] = release_matrix

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        storage_value = self._resolve_storage_metric(
            state=state,
            spec=spec,
            metric=self.parameters["storage_metric"],
        )
        inflow_index = bisect_right(self.parameters["inflow_breakpoints"], float(inflow_forecast))
        storage_index = bisect_right(self.parameters["storage_breakpoints"], float(storage_value))
        return float(self.parameters["release_matrix"][inflow_index][storage_index])

    @classmethod
    def get_optimization_spec(cls, *, context: dict[str, float]) -> ModuleOptimizationSpec:
        min_release = float(context["min_release"])
        max_release = float(context["max_release"])
        initial_release = cls._clip_value(
            float(context["initial_release_guess"]),
            lower=min_release,
            upper=max_release,
        )
        dimension = (len(context["joint_inflow_breakpoints"]) + 1) * (
            len(context["joint_storage_breakpoints"]) + 1
        )
        flat_start = tuple(initial_release for _ in range(dimension))
        matrix_start = (
            min_release,
            initial_release,
            max_release,
            initial_release,
            initial_release,
            max_release,
            max_release,
            max_release,
            max_release,
        )
        return ModuleOptimizationSpec(
            solver_kind="local_continuous",
            bounds=tuple((min_release, max_release) for _ in range(dimension)),
            initial_guesses=(flat_start, matrix_start[:dimension]),
            max_iterations=200,
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
        row_count = len(context["joint_inflow_breakpoints"]) + 1
        col_count = len(context["joint_storage_breakpoints"]) + 1
        raw_rows = [
            [float(vector[row_index * col_count + col_index]) for col_index in range(col_count)]
            for row_index in range(row_count)
        ]
        release_matrix = cls._project_monotone_release_matrix(
            raw_rows,
            lower=min_release,
            upper=max_release,
        )
        return {
            "storage_metric": "storage_ratio",
            "inflow_breakpoints": list(context["joint_inflow_breakpoints"]),
            "storage_breakpoints": list(context["joint_storage_breakpoints"]),
            "release_matrix": [
                [round(float(cell), 6) for cell in row]
                for row in release_matrix
            ],
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
                    "storage_metric": {
                        "type": "string",
                        "enum": ["storage", "storage_ratio"],
                        "default": "storage_ratio",
                    },
                    "inflow_breakpoints": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "storage_breakpoints": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "release_matrix": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "number", "minimum": 0},
                        },
                        "description": (
                            "2D release table with shape "
                            "[len(inflow_breakpoints)+1][len(storage_breakpoints)+1]."
                        ),
                    },
                },
                "required": [
                    "inflow_breakpoints",
                    "storage_breakpoints",
                    "release_matrix",
                ],
            },
        )
