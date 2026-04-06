"""Optimization service for flexible segmented release plans."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from ..domain.forecast import ForecastBundle
from ..domain.program import DispatchProgram, TimeHorizon
from ..domain.release import SegmentedReleaseSchedule
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .program import ProgramService


@dataclass(frozen=True)
class OptimizationProblem:
    """Inputs consumed by optimizer backend."""

    initial_state: ReservoirState
    forecast: ForecastBundle
    horizon: TimeHorizon
    control_interval_seconds: int
    constraints: dict[str, Any]
    objectives: dict[str, Any]
    directives: dict[str, Any]
    spec: ReservoirSpec


class OptimizerBackend(Protocol):
    """Optimizer backend protocol."""

    def optimize(self, problem: OptimizationProblem) -> list[float]:
        """Return segmented release values."""


class HeuristicOptimizerBackend:
    """Deterministic backend used for V1 and tests."""

    def optimize(self, problem: OptimizationProblem) -> list[float]:
        inflow_series = problem.forecast.get_series("inflow")
        if inflow_series is None:
            raise ValueError("Forecast must contain 'inflow' series")

        start = problem.horizon.start
        end = problem.horizon.end
        interval = problem.control_interval_seconds
        segment_count = int((end - start).total_seconds() // interval)

        index_map = {
            timestamp: value
            for timestamp, value in zip(inflow_series.timestamps, inflow_series.values)
        }

        min_env = float(problem.constraints.get("min_environmental_flow", 0.0))
        min_supply = float(problem.constraints.get("min_water_supply_flow", 0.0))
        lower_bound = max(min_env, min_supply)
        upper_bound = float(problem.constraints.get("max_outflow", float("inf")))
        max_ramp = problem.constraints.get("max_ramp_rate")
        max_ramp = float(max_ramp) if max_ramp is not None else None

        release_values: list[float] = []
        previous_release: float | None = None

        safety_factor = float(problem.directives.get("safety_factor", 0.9))
        safety_factor = max(0.0, min(safety_factor, 1.2))

        for segment in range(segment_count):
            seg_start = start + timedelta(seconds=segment * interval)
            seg_end = seg_start + timedelta(seconds=interval)

            sampled = [
                flow for timestamp, flow in index_map.items() if seg_start <= timestamp < seg_end
            ]
            if not sampled:
                sampled = [problem.initial_state.inflow]

            segment_inflow = sum(sampled) / len(sampled)
            proposed = segment_inflow * safety_factor

            headroom_discharge = problem.spec.discharge_capacity.get_max_discharge(
                max(problem.spec.dead_level, problem.initial_state.level)
            )
            proposed = min(proposed, headroom_discharge, upper_bound)
            proposed = max(proposed, lower_bound)

            if previous_release is not None and max_ramp is not None:
                min_allowed = previous_release - max_ramp
                max_allowed = previous_release + max_ramp
                proposed = max(min_allowed, min(max_allowed, proposed))

            release_values.append(float(proposed))
            previous_release = float(proposed)

        return release_values


class OptimizationService:
    """Create optimized flexible release programs via backend seam."""

    def __init__(
        self,
        spec: ReservoirSpec,
        program_service: ProgramService,
        backend: OptimizerBackend | None = None,
    ):
        self.spec = spec
        self.program_service = program_service
        self.backend = backend or HeuristicOptimizerBackend()

    def optimize_flexible_release_plan(
        self,
        *,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        horizon_hours: int,
        control_interval_seconds: int,
        constraints: dict[str, Any] | None = None,
        objectives: dict[str, Any] | None = None,
        directives: dict[str, Any] | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        optimizer_backend: str | None = None,
    ) -> tuple[DispatchProgram, SegmentedReleaseSchedule]:
        """Optimize and return a dispatch program with one flexible_release module."""
        if horizon_hours <= 0:
            raise ValueError("horizon_hours must be positive")
        if control_interval_seconds <= 0:
            raise ValueError("control_interval_seconds must be positive")

        start = initial_state.timestamp
        end = start + timedelta(hours=horizon_hours)
        horizon = TimeHorizon(start=start, end=end, time_step=3600)

        constraints = constraints or {}
        objectives = objectives or {}
        directives = directives or {}

        problem = OptimizationProblem(
            initial_state=initial_state,
            forecast=forecast,
            horizon=horizon,
            control_interval_seconds=control_interval_seconds,
            constraints=constraints,
            objectives=objectives,
            directives=directives,
            spec=self.spec,
        )

        backend = self._resolve_backend(optimizer_backend)
        release_values = backend.optimize(problem)

        schedule = SegmentedReleaseSchedule(
            start=start,
            end=end,
            control_interval_seconds=control_interval_seconds,
            release_values=release_values,
            min_release=float(constraints.get("min_release", 0.0)),
            max_release=(
                float(constraints["max_outflow"])
                if constraints.get("max_outflow") is not None
                else None
            ),
        )

        program = self.program_service.create_program(
            name=name or f"flex_plan_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            time_horizon=horizon,
            module_configs=[
                {
                    "module_type": "flexible_release",
                    "parameters": schedule.to_module_parameters(),
                }
            ],
            metadata={
                **(metadata or {}),
                "optimization": {
                    "constraints": constraints,
                    "objectives": objectives,
                    "directives": directives,
                    "control_interval_seconds": control_interval_seconds,
                },
            },
        )

        return program, schedule

    def _resolve_backend(self, optimizer_backend: str | None) -> OptimizerBackend:
        if optimizer_backend in (None, "heuristic"):
            return self.backend

        if optimizer_backend == "pymoo":
            if importlib.util.find_spec("pymoo") is None:
                raise ValueError(
                    "optimizer backend 'pymoo' requested but pymoo is not installed; "
                    "install with `uv add pymoo` or use optimizer_backend='heuristic'"
                )
            return self.backend

        raise ValueError(f"Unsupported optimizer backend: {optimizer_backend}")
