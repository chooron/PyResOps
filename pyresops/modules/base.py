"""Shared helpers for paper-aligned base release modules."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ..domain.module import ModuleInfo, OperationModule
from ..domain.reservoir import ReservoirSpec, ReservoirState


@dataclass(frozen=True)
class ModuleOptimizationSpec:
    """Family-local optimization parameterization for one module type."""

    solver_kind: str
    bounds: tuple[tuple[float, float], ...]
    initial_guesses: tuple[tuple[float, ...], ...]
    max_iterations: int = 80


class BaseOperationModule(OperationModule):
    """Base implementation for release modules."""

    MODULE_TYPE: str = "base"
    MODULE_NAME: str = "Base release module"
    MODULE_DESCRIPTION: str = "Base release module"

    def __init__(self, parameters: dict[str, Any]):
        super().__init__(parameters)
        self.validate_parameters()

    def validate_parameters(self) -> None:
        """Validate module parameters."""

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        return float(inflow_forecast)

    @classmethod
    def get_info(cls) -> ModuleInfo:
        return ModuleInfo(
            module_type=cls.MODULE_TYPE,
            name=cls.MODULE_NAME,
            description=cls.MODULE_DESCRIPTION,
            parameters_schema={},
        )

    @classmethod
    def get_optimization_spec(cls, *, context: dict[str, Any]) -> ModuleOptimizationSpec:
        raise NotImplementedError(f"{cls.__name__} does not expose an optimization spec")

    @classmethod
    def decode_optimization_vector(
        cls,
        vector: Sequence[float],
        *,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError(f"{cls.__name__} does not support parameter decoding")

    @staticmethod
    def _require_non_negative(name: str, value: float) -> None:
        if float(value) < 0:
            raise ValueError(f"{name} must be non-negative")

    @staticmethod
    def _coerce_float_list(name: str, values: Iterable[Any]) -> list[float]:
        coerced = [float(value) for value in values]
        if not coerced:
            raise ValueError(f"{name} must not be empty")
        return coerced

    @staticmethod
    def _validate_strictly_increasing(name: str, values: list[float]) -> None:
        if any(values[index] >= values[index + 1] for index in range(len(values) - 1)):
            raise ValueError(f"{name} must be strictly increasing")

    @staticmethod
    def _validate_piecewise_shape(
        *,
        breakpoints: list[float],
        release_values: list[float],
        breakpoint_name: str,
        release_name: str,
    ) -> None:
        BaseOperationModule._validate_strictly_increasing(breakpoint_name, breakpoints)
        if len(release_values) != len(breakpoints) + 1:
            raise ValueError(
                f"{release_name} must contain exactly len({breakpoint_name}) + 1 values"
            )
        for value in release_values:
            BaseOperationModule._require_non_negative(release_name, value)

    @staticmethod
    def _select_piecewise_value(value: float, breakpoints: list[float], outputs: list[float]) -> float:
        return float(outputs[bisect_right(breakpoints, float(value))])

    @staticmethod
    def _resolve_storage_metric(
        *,
        state: ReservoirState,
        spec: ReservoirSpec,
        metric: str,
    ) -> float:
        if metric == "storage_ratio":
            if spec.total_capacity <= 0:
                raise ValueError("ReservoirSpec.total_capacity must be positive")
            return float(state.storage) / float(spec.total_capacity)
        if metric == "storage":
            return float(state.storage)
        raise ValueError("metric must be either 'storage' or 'storage_ratio'")

    @staticmethod
    def _clip_value(value: float, *, lower: float, upper: float) -> float:
        return max(float(lower), min(float(upper), float(value)))

    @classmethod
    def _project_monotone_release_values(
        cls,
        values: Sequence[float],
        *,
        lower: float,
        upper: float,
    ) -> list[float]:
        projected: list[float] = []
        current = float(lower)
        for value in values:
            current = cls._clip_value(max(current, float(value)), lower=lower, upper=upper)
            projected.append(current)
        return projected

    @classmethod
    def _project_monotone_release_matrix(
        cls,
        rows: Sequence[Sequence[float]],
        *,
        lower: float,
        upper: float,
    ) -> list[list[float]]:
        matrix: list[list[float]] = []
        for row_index, row in enumerate(rows):
            projected_row: list[float] = []
            for col_index, value in enumerate(row):
                candidate = cls._clip_value(float(value), lower=lower, upper=upper)
                if row_index > 0:
                    candidate = max(candidate, matrix[row_index - 1][col_index])
                if col_index > 0:
                    candidate = max(candidate, projected_row[col_index - 1])
                projected_row.append(cls._clip_value(candidate, lower=lower, upper=upper))
            matrix.append(projected_row)
        return matrix
