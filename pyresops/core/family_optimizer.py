"""Continuous solver helpers for release-family parameter optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy.optimize import minimize, minimize_scalar


@dataclass(frozen=True)
class FamilyOptimizationRun:
    """Outcome returned by the generic continuous family optimizer."""

    best_vector: tuple[float, ...]
    best_objective: float
    solver_method: str


class ContinuousFamilyOptimizer:
    """Run SciPy-based optimization for a family-local parameterization."""

    def solve(
        self,
        *,
        solver_kind: str,
        bounds: Sequence[tuple[float, float]],
        initial_guesses: Sequence[Sequence[float]],
        objective_fn: Callable[[Sequence[float]], float],
        max_iterations: int,
    ) -> FamilyOptimizationRun:
        if not bounds:
            raise ValueError("Optimization bounds must not be empty")

        normalized_bounds = tuple((float(lower), float(upper)) for lower, upper in bounds)
        best_vector = tuple((lower + upper) / 2.0 for lower, upper in normalized_bounds)
        best_objective = float(objective_fn(best_vector))
        best_method = "initial_guess"

        if solver_kind == "bounded_scalar":
            scalar_bounds = normalized_bounds[0]
            scalar_result = minimize_scalar(
                lambda value: float(objective_fn((float(value),))),
                bounds=scalar_bounds,
                method="bounded",
                options={"maxiter": max_iterations},
            )
            candidate_vector = (float(scalar_result.x),)
            candidate_objective = float(objective_fn(candidate_vector))
            if candidate_objective < best_objective:
                best_vector = candidate_vector
                best_objective = candidate_objective
                best_method = "scipy.minimize_scalar"
            return FamilyOptimizationRun(
                best_vector=best_vector,
                best_objective=best_objective,
                solver_method=best_method,
            )

        starts = list(initial_guesses) or [best_vector]
        for guess in starts:
            normalized_guess = np.asarray([float(value) for value in guess], dtype=float)
            minimize_result = minimize(
                lambda vector: float(objective_fn(vector)),
                normalized_guess,
                method="Powell",
                bounds=normalized_bounds,
                options={"maxiter": max_iterations, "xtol": 1e-3, "ftol": 1e-3},
            )
            candidate_vector = tuple(float(value) for value in minimize_result.x)
            candidate_objective = float(objective_fn(candidate_vector))
            if candidate_objective < best_objective:
                best_vector = candidate_vector
                best_objective = candidate_objective
                best_method = "scipy.minimize[Powell]"

        return FamilyOptimizationRun(
            best_vector=best_vector,
            best_objective=best_objective,
            solver_method=best_method,
        )
