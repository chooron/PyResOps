"""Family-oriented release optimization service."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

import numpy as np

from ..core import ContinuousFamilyOptimizer, DecisionOrchestrator, SimulationEngine
from ..domain.constraint import Constraint, ConstraintSet
from ..domain.forecast import ForecastBundle
from ..domain.policy import PolicyBundle
from ..domain.program import DispatchProgram, TimeHorizon
from ..domain.reservoir import ReservoirSpec, ReservoirState
from ..domain.result import EvaluationResult, SimulationResult
from ..modules import ALLOWED_BASE_RELEASE_MODULE_TYPES
from ..plugins import PluginBundleConfig, PluginManager
from .evaluation import EvaluationService
from .program import ProgramService


DEFAULT_FAMILY_ORDER = [
    "constant_release",
    "inflow_linear_release",
    "inflow_piecewise_constant_release",
    "storage_piecewise_constant_release",
    "storage_nonlinear_release",
    "joint_driven_release",
]


@dataclass(frozen=True)
class ReleaseOptimizationCandidate:
    module_type: str
    module_parameters: dict[str, Any]
    simulation_result: SimulationResult
    evaluation_result: EvaluationResult
    violations: list[dict[str, Any]]
    unmet_task_constraints: list[dict[str, Any]]
    objective_score: float
    solve_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return not self.violations and not self.unmet_task_constraints

    def to_dict(self) -> dict[str, Any]:
        final_level = self.simulation_result.snapshots[-1].level if self.simulation_result.snapshots else None
        payload = {
            "module_type": self.module_type,
            "module_parameters": dict(self.module_parameters),
            "feasible": self.feasible,
            "objective_score": round(float(self.objective_score), 6),
            "violations": list(self.violations),
            "unmet_task_constraints": list(self.unmet_task_constraints),
            "final_level_m": None if final_level is None else round(float(final_level), 3),
            "avg_outflow_m3s": round(float(self.simulation_result.avg_outflow), 3),
            "overall_score": round(float(self.evaluation_result.overall_score), 6),
        }
        if self.solve_metadata:
            payload["solve_metadata"] = {
                key: round(float(value), 6) if isinstance(value, float) else value
                for key, value in self.solve_metadata.items()
            }
        return payload


@dataclass(frozen=True)
class ReleaseOptimizationResult:
    program: DispatchProgram
    selected_candidate: ReleaseOptimizationCandidate
    family_attempts: list[dict[str, Any]] = field(default_factory=list)
    requested_module_type: str | None = None
    fallback_applied: bool = False
    solution_mode: str = "feasible"
    plugin_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "program_id": self.program.id,
            "selected_module_type": self.selected_candidate.module_type,
            "selected_module_parameters": dict(self.selected_candidate.module_parameters),
            "feasible_solution_found": self.selected_candidate.feasible,
            "fallback_applied": self.fallback_applied,
            "solution_mode": self.solution_mode,
            "requested_module_type": self.requested_module_type,
            "family_attempts": list(self.family_attempts),
        }
        if self.plugin_results:
            payload["plugin_results"] = dict(self.plugin_results)
        return payload


class OptimizationService:
    """Optimize module parameters per family and select the best admissible family."""

    def __init__(
        self,
        spec: ReservoirSpec,
        program_service: ProgramService,
        evaluation_service: EvaluationService | None = None,
        plugin_manager: PluginManager | None = None,
        default_plugin_bundle: PluginBundleConfig | None = None,
    ):
        self.spec = spec
        self.program_service = program_service
        self.evaluation_service = evaluation_service or EvaluationService(spec)
        self.family_optimizer = ContinuousFamilyOptimizer()
        self.plugin_manager = plugin_manager
        self.default_plugin_bundle = default_plugin_bundle

    def optimize_release_plan(
        self,
        *,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        constraints: dict[str, Any] | None = None,
        objectives: dict[str, Any] | None = None,
        task_constraints: dict[str, Any] | None = None,
        directives: dict[str, Any] | None = None,
        allowed_module_types: list[str] | None = None,
        requested_module_type: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
        policy_bundle: PolicyBundle | None = None,
        plugin_bundle: PluginBundleConfig | None = None,
    ) -> ReleaseOptimizationResult:
        constraints = constraints or {}
        objectives = objectives or {}
        task_constraints = task_constraints or {}
        directives = directives or {}
        active_plugin_bundle = plugin_bundle or self.default_plugin_bundle
        resolved_forecast = forecast
        prepared_plugin_results: dict[str, Any] = {}
        if self.plugin_manager and active_plugin_bundle:
            (
                resolved_forecast,
                prepared_plugin_results,
                active_plugin_bundle,
            ) = self.plugin_manager.prepare_forecast(
                forecast=forecast,
                initial_state=initial_state,
                plugin_bundle=active_plugin_bundle,
            )

        family_order = self._resolve_family_order(
            requested_module_type=requested_module_type,
            allowed_module_types=allowed_module_types,
        )
        resolved_policy = self._resolve_policy_bundle(
            constraints=constraints,
            objectives=objectives,
            directives=directives,
            policy_bundle=policy_bundle,
        )

        best_effort_candidate: ReleaseOptimizationCandidate | None = None
        best_effort_family: str | None = None
        family_attempts: list[dict[str, Any]] = []

        for module_type in family_order:
            try:
                candidate = self._solve_family(
                    module_type=module_type,
                    initial_state=initial_state,
                    forecast=resolved_forecast,
                    policy_bundle=resolved_policy,
                    objectives=objectives,
                    task_constraints=task_constraints,
                    plugin_bundle=active_plugin_bundle,
                )
            except Exception as exc:
                family_attempts.append(
                    {
                        "module_type": module_type,
                        "candidate_count": 0,
                        "selected_candidate": None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            family_attempts.append(
                {
                    "module_type": module_type,
                    "candidate_count": int(candidate.solve_metadata.get("evaluation_count", 1)),
                    "solver_method": candidate.solve_metadata.get("solver_method"),
                    "selected_candidate": candidate.to_dict(),
                }
            )
            if candidate.feasible:
                program = self._build_program(
                    module_type=module_type,
                    module_parameters=candidate.module_parameters,
                    initial_state=initial_state,
                    forecast=resolved_forecast,
                    name=name,
                    metadata=self._merge_program_metadata(metadata, prepared_plugin_results),
                )
                return ReleaseOptimizationResult(
                    program=program,
                    selected_candidate=candidate,
                    family_attempts=family_attempts,
                    requested_module_type=requested_module_type,
                    fallback_applied=False,
                    solution_mode="feasible",
                    plugin_results=prepared_plugin_results,
                )

            if (
                best_effort_candidate is None
                or candidate.objective_score > best_effort_candidate.objective_score
            ):
                best_effort_candidate = candidate
                best_effort_family = module_type

        if best_effort_candidate is None or best_effort_family is None:
            raise ValueError("No optimization candidates were generated for the requested release families")

        program = self._build_program(
            module_type=best_effort_family,
            module_parameters=best_effort_candidate.module_parameters,
            initial_state=initial_state,
            forecast=resolved_forecast,
            name=name,
            metadata=self._merge_program_metadata(metadata, prepared_plugin_results),
        )
        return ReleaseOptimizationResult(
            program=program,
            selected_candidate=best_effort_candidate,
            family_attempts=family_attempts,
            requested_module_type=requested_module_type,
            fallback_applied=True,
            solution_mode="best_effort",
            plugin_results=prepared_plugin_results,
        )

    def _resolve_family_order(
        self,
        *,
        requested_module_type: str | None,
        allowed_module_types: list[str] | None,
    ) -> list[str]:
        if requested_module_type is not None:
            if requested_module_type not in ALLOWED_BASE_RELEASE_MODULE_TYPES:
                raise ValueError(f"Unsupported requested_module_type: {requested_module_type}")
            return [requested_module_type]

        if not allowed_module_types:
            return list(DEFAULT_FAMILY_ORDER)

        allowed: list[str] = []
        for item in allowed_module_types:
            if item not in ALLOWED_BASE_RELEASE_MODULE_TYPES:
                continue
            if item in allowed:
                continue
            allowed.append(item)
        if not allowed:
            raise ValueError("allowed_module_types did not contain any supported base release family")
        return allowed

    def _resolve_policy_bundle(
        self,
        *,
        constraints: dict[str, Any],
        objectives: dict[str, Any],
        directives: dict[str, Any],
        policy_bundle: PolicyBundle | None,
    ) -> PolicyBundle:
        if policy_bundle is None:
            return self._build_policy_bundle(constraints, objectives, directives)

        resolved = policy_bundle.model_copy(deep=True)
        overlay = self._build_policy_bundle(constraints, objectives, directives)
        if overlay.constraints.constraints:
            merged_constraints = {
                constraint.id: constraint for constraint in resolved.constraints.constraints
            }
            for constraint in overlay.constraints.constraints:
                merged_constraints[constraint.id] = constraint
            resolved.constraints = ConstraintSet(constraints=list(merged_constraints.values()))
        resolved.objectives = {**resolved.objectives, **objectives}
        resolved.directives = {**resolved.directives, **directives}

        source_constraints = self._constraint_hints_from_policy_bundle(resolved)
        source_constraints.update(constraints)
        resolved.metadata = dict(resolved.metadata)
        resolved.metadata["source_constraints"] = source_constraints
        return resolved

    def _solve_family(
        self,
        *,
        module_type: str,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        policy_bundle: PolicyBundle,
        objectives: dict[str, Any],
        task_constraints: dict[str, Any],
        plugin_bundle: PluginBundleConfig | None,
    ) -> ReleaseOptimizationCandidate:
        module_registry = self.program_service.get_module_registry()
        module_class = module_registry[module_type]
        context = self._build_module_optimization_context(
            module_type=module_type,
            initial_state=initial_state,
            forecast=forecast,
            policy_bundle=policy_bundle,
            objectives=objectives,
            task_constraints=task_constraints,
        )
        optimization_spec = module_class.get_optimization_spec(context=context)
        local_program_service = ProgramService()
        engine = SimulationEngine(self.spec)
        candidate_cache: dict[str, ReleaseOptimizationCandidate] = {}

        def get_candidate(vector: Any) -> ReleaseOptimizationCandidate:
            parameters = module_class.decode_optimization_vector(vector, context=context)
            cache_key = self._candidate_cache_key(parameters)
            if cache_key not in candidate_cache:
                candidate_cache[cache_key] = self._evaluate_candidate(
                    module_type=module_type,
                    module_parameters=parameters,
                    initial_state=initial_state,
                    forecast=forecast,
                    policy_bundle=policy_bundle,
                    objectives=objectives,
                    task_constraints=task_constraints,
                    local_program_service=local_program_service,
                    engine=engine,
                    plugin_bundle=plugin_bundle,
                )
            return candidate_cache[cache_key]

        solve_run = self.family_optimizer.solve(
            solver_kind=optimization_spec.solver_kind,
            bounds=optimization_spec.bounds,
            initial_guesses=optimization_spec.initial_guesses,
            objective_fn=lambda vector: -get_candidate(vector).objective_score,
            max_iterations=optimization_spec.max_iterations,
        )

        if not candidate_cache:
            fallback_parameters = module_class.decode_optimization_vector(
                solve_run.best_vector,
                context=context,
            )
            fallback_key = self._candidate_cache_key(fallback_parameters)
            candidate_cache[fallback_key] = self._evaluate_candidate(
                module_type=module_type,
                module_parameters=fallback_parameters,
                initial_state=initial_state,
                forecast=forecast,
                policy_bundle=policy_bundle,
                objectives=objectives,
                task_constraints=task_constraints,
                local_program_service=local_program_service,
                engine=engine,
                plugin_bundle=plugin_bundle,
            )
        best_candidate = max(candidate_cache.values(), key=lambda item: item.objective_score)
        return replace(
            best_candidate,
            solve_metadata={
                **best_candidate.solve_metadata,
                "solver_method": solve_run.solver_method,
                "evaluation_count": len(candidate_cache),
            },
        )

    def _evaluate_candidate(
        self,
        *,
        module_type: str,
        module_parameters: dict[str, Any],
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        policy_bundle: PolicyBundle,
        objectives: dict[str, Any],
        task_constraints: dict[str, Any],
        local_program_service: ProgramService,
        engine: SimulationEngine,
        plugin_bundle: PluginBundleConfig | None,
    ) -> ReleaseOptimizationCandidate:
        program = local_program_service.create_program(
            name=f"opt_{module_type}",
            time_horizon=self._build_horizon(initial_state, forecast),
            module_configs=[{"module_type": module_type, "parameters": module_parameters}],
        )
        simulation_result = engine.simulate(
            program,
            initial_state.copy_with_update(),
            forecast,
            {module_type: local_program_service.get_module_registry()[module_type](module_parameters)},
            policy_bundle=policy_bundle,
            orchestrator=DecisionOrchestrator(),
            plugin_manager=self.plugin_manager,
            plugin_bundle=plugin_bundle,
        )
        evaluation_result = self.evaluation_service.evaluate(
            simulation_result,
            constraint_set=policy_bundle.constraints,
            proxy_options=self._build_proxy_options(
                policy_bundle=policy_bundle,
                initial_state=initial_state,
            ),
        )
        violations = self._merge_legacy_violations(
            evaluation_result.constraint_violations,
            simulation_result.metadata.get("policy_global_violations", []),
        )
        unmet_task_constraints = self._evaluate_task_constraints(simulation_result, task_constraints)
        adjustment_count, fallback_count = self._extract_adjustment_stats(simulation_result)
        hard_gap = self._compute_violation_gap(violations)
        task_gap = self._compute_task_gap(unmet_task_constraints)
        objective_score = self._score_candidate(
            result=simulation_result,
            evaluation_result=evaluation_result,
            objectives=objectives,
            module_type=module_type,
            violations=violations,
            unmet_task_constraints=unmet_task_constraints,
            task_constraints=task_constraints,
            adjustment_count=adjustment_count,
            fallback_count=fallback_count,
            constraint_hints=self._constraint_hints_from_policy_bundle(policy_bundle),
        )
        return ReleaseOptimizationCandidate(
            module_type=module_type,
            module_parameters=module_parameters,
            simulation_result=simulation_result,
            evaluation_result=evaluation_result,
            violations=violations,
            unmet_task_constraints=unmet_task_constraints,
            objective_score=objective_score,
            solve_metadata={
                "hard_gap": hard_gap,
                "task_gap": task_gap,
                "adjustment_count": adjustment_count,
                "fallback_count": fallback_count,
            },
        )

    def _build_program(
        self,
        *,
        module_type: str,
        module_parameters: dict[str, Any],
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        name: str | None,
        metadata: dict[str, Any] | None,
    ) -> DispatchProgram:
        return self.program_service.create_program(
            name=name or f"optimized_{module_type}",
            time_horizon=self._build_horizon(initial_state, forecast),
            module_configs=[{"module_type": module_type, "parameters": module_parameters}],
            metadata=metadata or {},
        )

    @staticmethod
    def _merge_program_metadata(
        metadata: dict[str, Any] | None,
        plugin_results: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = dict(metadata or {})
        if plugin_results:
            resolved["plugin_results"] = dict(plugin_results)
        return resolved

    def _build_horizon(self, initial_state: ReservoirState, forecast: ForecastBundle) -> TimeHorizon:
        inflow_series = forecast.get_series("inflow")
        if inflow_series is None or not inflow_series.timestamps:
            raise ValueError("Forecast must contain an inflow series with timestamps")
        if len(inflow_series.timestamps) >= 2:
            time_step = int((inflow_series.timestamps[1] - inflow_series.timestamps[0]).total_seconds())
        else:
            time_step = 3600
        if time_step <= 0:
            raise ValueError("Forecast timestamps must be strictly increasing")
        return TimeHorizon(
            start=initial_state.timestamp,
            end=inflow_series.timestamps[-1] + timedelta(seconds=time_step),
            time_step=time_step,
        )

    def _build_policy_bundle(
        self,
        constraints: dict[str, Any],
        objectives: dict[str, Any],
        directives: dict[str, Any],
    ) -> PolicyBundle:
        items: list[Constraint] = []

        min_flow = self._first_defined(
            constraints,
            "ecological_min_flow",
            "min_release",
            "min_environmental_flow",
            "eco_min_flow",
        )
        if min_flow is not None:
            items.append(
                Constraint(
                    id="ecological_min_flow",
                    name="Ecological minimum flow",
                    constraint_type="ecological_min_flow",
                    parameters={"min_flow": float(min_flow)},
                    priority=100,
                    scope="both",
                )
            )

        max_flow = self._first_defined(
            constraints,
            "max_release",
            "max_outflow",
            "downstream_limit",
        )
        if max_flow is not None:
            items.append(
                Constraint(
                    id="flow_max",
                    name="Maximum release",
                    constraint_type="flow_max",
                    parameters={"max_flow": float(max_flow)},
                    priority=90,
                    scope="both",
                )
            )

        max_level = self._first_defined(constraints, "max_level", "level_max")
        if max_level is not None:
            items.append(
                Constraint(
                    id="level_max",
                    name="Maximum level",
                    constraint_type="level_max",
                    parameters={"max_level": float(max_level)},
                    priority=95,
                    scope="both",
                )
            )

        min_level = self._first_defined(constraints, "min_level", "level_min")
        if min_level is not None:
            items.append(
                Constraint(
                    id="level_min",
                    name="Minimum level",
                    constraint_type="level_min",
                    parameters={"min_level": float(min_level)},
                    priority=95,
                    scope="both",
                )
            )

        ramp = self._first_defined(constraints, "ramp_rate_max", "max_ramp_rate")
        if ramp is not None:
            items.append(
                Constraint(
                    id="ramp_rate_max",
                    name="Ramp rate max",
                    constraint_type="ramp_rate_max",
                    parameters={"max_ramp": float(ramp)},
                    priority=85,
                    scope="step",
                )
            )

        downstream_limit = constraints.get("downstream_flow_limit")
        if downstream_limit is not None:
            items.append(
                Constraint(
                    id="downstream_flow_limit",
                    name="Downstream flow limit",
                    constraint_type="downstream_flow_limit",
                    parameters={"max_section_flow": float(downstream_limit)},
                    priority=88,
                    scope="step",
                )
            )

        return PolicyBundle(
            constraints=ConstraintSet(constraints=items),
            objectives=dict(objectives),
            directives=dict(directives),
            metadata={"source_constraints": dict(constraints)},
        )

    def _build_module_optimization_context(
        self,
        *,
        module_type: str,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        policy_bundle: PolicyBundle,
        objectives: dict[str, Any],
        task_constraints: dict[str, Any],
    ) -> dict[str, Any]:
        inflow_series = forecast.get_series("inflow")
        if inflow_series is None or not inflow_series.values:
            raise ValueError("Forecast must contain inflow values")

        inflows = [float(value) for value in inflow_series.values]
        constraint_hints = self._constraint_hints_from_policy_bundle(policy_bundle)
        min_release = max(
            0.0,
            float(
                self._first_defined(
                    constraint_hints,
                    "ecological_min_flow",
                    "min_release",
                    "min_environmental_flow",
                    "eco_min_flow",
                )
                or 0.0
            ),
        )
        natural_max_release = float(self.spec.discharge_capacity.get_max_discharge(initial_state.level))
        constraint_max = self._first_defined(
            constraint_hints,
            "max_release",
            "max_outflow",
            "downstream_limit",
            "downstream_flow_limit",
        )
        max_release = (
            min(natural_max_release, float(constraint_max))
            if constraint_max is not None
            else natural_max_release
        )
        if max_release < min_release:
            max_release = min_release

        inflow_breakpoints = self._build_quantile_breakpoints(inflows, quantiles=(1 / 3, 2 / 3))
        initial_release_guess = self._estimate_initial_release(
            initial_state=initial_state,
            forecast=forecast,
            min_release=min_release,
            max_release=max_release,
            objectives=objectives,
            task_constraints=task_constraints,
        )
        context = {
            "module_type": module_type,
            "initial_state": initial_state,
            "forecast": forecast,
            "policy_bundle": policy_bundle,
            "inflows": inflows,
            "inflow_min": min(inflows),
            "inflow_mean": sum(inflows) / len(inflows),
            "inflow_max": max(inflows),
            "inflow_breakpoints": inflow_breakpoints,
            "joint_inflow_breakpoints": inflow_breakpoints,
            "storage_piecewise_breakpoints": [0.45, 0.75],
            "storage_nonlinear_control_points": [0.0, 0.5, 0.75, 1.0],
            "joint_storage_breakpoints": [0.6, 0.8],
            "min_release": min_release,
            "max_release": max_release,
            "initial_release_guess": initial_release_guess,
            "constraint_hints": constraint_hints,
        }
        return context

    def _estimate_initial_release(
        self,
        *,
        initial_state: ReservoirState,
        forecast: ForecastBundle,
        min_release: float,
        max_release: float,
        objectives: dict[str, Any],
        task_constraints: dict[str, Any],
    ) -> float:
        inflow_series = forecast.get_series("inflow")
        if inflow_series is None or not inflow_series.values:
            return min_release

        mean_inflow = sum(float(value) for value in inflow_series.values) / len(inflow_series.values)
        target_level = self._resolve_target_level_reference(
            objectives=objectives,
            task_constraints=task_constraints,
        )
        if target_level is None:
            return self._clip_value(mean_inflow, lower=min_release, upper=max_release)

        target_storage = float(self.spec.level_storage_curve.get_storage(target_level))
        if len(inflow_series.timestamps) >= 2:
            dt = int((inflow_series.timestamps[1] - inflow_series.timestamps[0]).total_seconds())
        else:
            dt = 3600
        total_seconds = max(dt * len(inflow_series.values), 1)
        required_release = mean_inflow + ((initial_state.storage - target_storage) * 1e8) / total_seconds
        return self._clip_value(required_release, lower=min_release, upper=max_release)

    def _build_proxy_options(
        self,
        *,
        policy_bundle: PolicyBundle,
        initial_state: ReservoirState,
    ) -> dict[str, Any]:
        constraint_hints = self._constraint_hints_from_policy_bundle(policy_bundle)
        env_min_flow = self._first_defined(
            constraint_hints,
            "ecological_min_flow",
            "min_release",
            "min_environmental_flow",
            "eco_min_flow",
        )
        return {
            "env_min_flow": 0.0 if env_min_flow is None else float(env_min_flow),
            "max_ramp_rate": self._first_defined(constraint_hints, "ramp_rate_max", "max_ramp_rate"),
            "tailwater_level": float(policy_bundle.directives.get("tailwater_level", initial_state.level - 10.0)),
        }

    def _evaluate_task_constraints(
        self,
        result: SimulationResult,
        task_constraints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not result.snapshots:
            return [
                {
                    "constraint_id": "snapshots",
                    "message": "simulation produced no snapshots",
                    "gap": 1.0,
                }
            ]

        final_level = float(result.snapshots[-1].level)
        unmet: list[dict[str, Any]] = []

        target_level = self._first_defined(task_constraints, "target_level", "target_level_m")
        tolerance = float(task_constraints.get("target_tolerance", task_constraints.get("target_tolerance_m", 0.0)))
        if target_level is not None and final_level > float(target_level) + tolerance:
            exceedance = final_level - float(target_level) - tolerance
            unmet.append(
                {
                    "constraint_id": "target_level",
                    "message": (
                        f"final level {final_level:.3f}m exceeds target {float(target_level):.3f}m "
                        f"with tolerance {tolerance:.3f}m"
                    ),
                    "gap": exceedance / max(tolerance, 0.1),
                }
            )

        max_final_level = task_constraints.get("max_final_level")
        if max_final_level is not None and final_level > float(max_final_level):
            unmet.append(
                {
                    "constraint_id": "max_final_level",
                    "message": f"final level {final_level:.3f}m exceeds {float(max_final_level):.3f}m",
                    "gap": final_level - float(max_final_level),
                }
            )

        min_final_level = task_constraints.get("min_final_level")
        if min_final_level is not None and final_level < float(min_final_level):
            unmet.append(
                {
                    "constraint_id": "min_final_level",
                    "message": f"final level {final_level:.3f}m is below {float(min_final_level):.3f}m",
                    "gap": float(min_final_level) - final_level,
                }
            )

        return unmet

    def _score_candidate(
        self,
        *,
        result: SimulationResult,
        evaluation_result: EvaluationResult,
        objectives: dict[str, Any],
        module_type: str,
        violations: list[dict[str, Any]],
        unmet_task_constraints: list[dict[str, Any]],
        task_constraints: dict[str, Any],
        adjustment_count: int,
        fallback_count: int,
        constraint_hints: dict[str, Any],
    ) -> float:
        hard_gap = self._compute_violation_gap(violations)
        task_gap = self._compute_task_gap(unmet_task_constraints)
        adjustment_penalty = (
            float(adjustment_count) + 2.0 * float(fallback_count)
        ) / max(len(result.snapshots), 1)
        final_level = float(result.snapshots[-1].level) if result.snapshots else float("inf")
        avg_outflow = float(result.avg_outflow)
        max_release_hint = self._first_defined(
            constraint_hints,
            "max_release",
            "max_outflow",
            "downstream_limit",
            "downstream_flow_limit",
        )
        release_scale = max(float(max_release_hint or avg_outflow or 1.0), 1.0)

        primary_cost = 0.0
        target_level = self._resolve_target_level_reference(
            objectives=objectives,
            task_constraints=task_constraints,
        )
        if target_level is not None:
            primary_cost += abs(final_level - target_level)
            primary_cost += 0.001 * (avg_outflow / release_scale)
        elif objectives.get("maximize_generation") or objectives.get("objective_family") == "power_generation":
            primary_cost += 1.0 - (float(evaluation_result.power_generation_score) / 100.0)
        else:
            primary_cost += avg_outflow / release_scale

        if objectives.get("maximize_generation") or objectives.get("objective_family") == "power_generation":
            primary_cost -= 0.05 * (float(evaluation_result.power_generation_score) / 100.0)

        secondary_credit = (
            0.01 * (float(evaluation_result.overall_score) / 100.0)
            if target_level is not None
            else 0.10 * (float(evaluation_result.overall_score) / 100.0)
        )
        family_penalty = 1e-6 * DEFAULT_FAMILY_ORDER.index(module_type)
        total_cost = (
            10000.0 * hard_gap
            + 1000.0 * task_gap
            + 5.0 * adjustment_penalty
            + primary_cost
            + family_penalty
            - secondary_credit
        )
        return -total_cost

    def _resolve_target_level_reference(
        self,
        *,
        objectives: dict[str, Any],
        task_constraints: dict[str, Any],
    ) -> float | None:
        target_level = self._resolve_target_level_objective(objectives)
        if target_level is not None:
            return target_level

        target_level = self._first_defined(task_constraints, "target_level", "target_level_m")
        return None if target_level is None else float(target_level)

    def _resolve_target_level_objective(self, objectives: dict[str, Any]) -> float | None:
        target_level = self._first_defined(objectives, "target_level", "target_level_m")
        if target_level is not None:
            return float(target_level)

        curve = objectives.get("target_level_curve")
        if isinstance(curve, list) and curve:
            last_point = curve[-1]
            if isinstance(last_point, dict) and self._first_defined(last_point, "level", "target_level") is not None:
                return float(self._first_defined(last_point, "level", "target_level"))
            try:
                return float(last_point)
            except (TypeError, ValueError):
                return None
        return None

    def _constraint_hints_from_policy_bundle(self, policy_bundle: PolicyBundle) -> dict[str, Any]:
        hints = dict(policy_bundle.metadata.get("source_constraints", {}))
        for constraint in policy_bundle.constraints.constraints:
            if constraint.constraint_type == "ecological_min_flow":
                hints.setdefault("ecological_min_flow", constraint.parameters.get("min_flow"))
            elif constraint.constraint_type == "flow_min":
                hints.setdefault("min_release", constraint.parameters.get("min_flow"))
                hints.setdefault("min_environmental_flow", constraint.parameters.get("min_flow"))
            elif constraint.constraint_type == "flow_max":
                hints.setdefault("max_release", constraint.parameters.get("max_flow"))
                hints.setdefault("max_outflow", constraint.parameters.get("max_flow"))
            elif constraint.constraint_type == "level_max":
                hints.setdefault("max_level", constraint.parameters.get("max_level"))
            elif constraint.constraint_type == "level_min":
                hints.setdefault("min_level", constraint.parameters.get("min_level"))
            elif constraint.constraint_type == "ramp_rate_max":
                hints.setdefault("ramp_rate_max", constraint.parameters.get("max_ramp"))
                hints.setdefault("max_ramp_rate", constraint.parameters.get("max_ramp"))
            elif constraint.constraint_type == "downstream_flow_limit":
                hints.setdefault("downstream_flow_limit", constraint.parameters.get("max_section_flow"))
                hints.setdefault("downstream_limit", constraint.parameters.get("max_section_flow"))
        return hints

    @staticmethod
    def _candidate_cache_key(parameters: dict[str, Any]) -> str:
        return json.dumps(parameters, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _merge_legacy_violations(*violation_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
        for group in violation_groups:
            for item in group or []:
                key = (
                    item.get("constraint_id"),
                    item.get("violation_type"),
                    item.get("scope"),
                    item.get("step_index"),
                )
                deduplicated[key] = item
        return list(deduplicated.values())

    @staticmethod
    def _extract_adjustment_stats(result: SimulationResult) -> tuple[int, int]:
        adjustment_count = 0
        fallback_count = 0
        for snapshot in result.snapshots:
            metadata = snapshot.metadata or {}
            adjustment_count += len(metadata.get("adjustments", []))
            if metadata.get("fallback_used"):
                fallback_count += 1
        return adjustment_count, fallback_count

    @staticmethod
    def _compute_violation_gap(violations: list[dict[str, Any]]) -> float:
        gap = 0.0
        for violation in violations:
            value = violation.get("value")
            limit = violation.get("limit")
            if value is None or limit is None:
                gap += 1.0
                continue
            gap += OptimizationService._normalized_gap(float(value), float(limit))
        return gap

    @staticmethod
    def _compute_task_gap(unmet_task_constraints: list[dict[str, Any]]) -> float:
        return sum(float(item.get("gap", 1.0)) for item in unmet_task_constraints)

    @staticmethod
    def _normalized_gap(value: float, limit: float) -> float:
        scale = max(abs(float(limit)), 1.0)
        return abs(float(value) - float(limit)) / scale

    @staticmethod
    def _clip_value(value: float, *, lower: float, upper: float) -> float:
        return max(float(lower), min(float(upper), float(value)))

    @staticmethod
    def _build_quantile_breakpoints(values: list[float], quantiles: tuple[float, ...]) -> list[float]:
        if not values:
            raise ValueError("values must not be empty")
        raw = [float(np.quantile(values, quantile)) for quantile in quantiles]
        normalized: list[float] = []
        for value in raw:
            if not normalized or abs(value - normalized[-1]) > 1e-6:
                normalized.append(value)
        return normalized or [float(values[0])]

    @staticmethod
    def _first_defined(mapping: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = mapping.get(key)
            if value is not None:
                return value
        return None
