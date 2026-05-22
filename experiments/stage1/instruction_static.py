"""Instruction-conditioned static extension — Stage 1 direct-service runner.

Evaluates whether PyResOps can execute operator-specified release-family
commands and operation-interval commands under deterministic service execution
for all 41 retained Tankeng flood events.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from pyresops.agents.specs import load_default_experiment_spec
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import ReservoirState
from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
from pyresops.services import OptimizationService, ProgramService, SimulationService
from pyresops.services.optimization import (
    ReleaseOptimizationCandidate,
    ReleaseOptimizationResult,
)

from experiments.data_adapters.real_events import RealEventDataAdapter
from experiments.stage1.classify import classify_event
from experiments.stage1.constraints import (
    build_tankan_constraints,
    get_flood_limit,
    get_season_name,
)
from experiments.stage1.downstream import MuskingumDownstreamCheck
from experiments.stage1.metrics import extract_unified_metrics


EXTENSION_TYPE = "instruction_conditioned_static"
VALID_OPERATION_INTERVALS_H = {3, 6, 12}

RELEASE_FAMILIES = [
    "constant_release",
    "inflow_piecewise_constant_release",
    "inflow_linear_release",
    "storage_piecewise_constant_release",
    "storage_nonlinear_release",
    "joint_driven_release",
]


def build_tankeng_constraints(month: int, day: int = 1) -> dict[str, Any]:
    """Return constraint dict for Tankeng Reservoir (wraps legacy build_tankan_constraints)."""
    return build_tankan_constraints(month, day)


def make_config_hash(
    event_id: str,
    specified_family: str,
    operation_interval_h: int,
    constraints_dict: dict[str, Any],
) -> str:
    """Return 12-char SHA-256 hex digest sensitive to event, family, interval, and constraints."""
    payload = (
        event_id
        + specified_family
        + str(operation_interval_h)
        + json.dumps(constraints_dict, sort_keys=True)
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def quantize_to_interval(release_series: list[float], k: int) -> list[float]:
    """Block-mean quantization: replace each block of k steps with the block mean.

    The last block may be shorter than k. Returns a new list of the same length.
    """
    if k <= 1:
        return list(release_series)
    n = len(release_series)
    result: list[float] = []
    i = 0
    while i < n:
        block = release_series[i : i + k]
        mean_val = sum(block) / len(block)
        result.extend([mean_val] * len(block))
        i += k
    return result


def check_interval_compliance(release_series: list[float], k: int) -> bool:
    """Return True if all values within each block of k steps are equal (within 1e-6).

    The last block may be shorter than k.
    """
    if k <= 1:
        return True
    n = len(release_series)
    i = 0
    while i < n:
        block = release_series[i : i + k]
        ref = block[0]
        for val in block[1:]:
            if abs(val - ref) > 1e-6:
                return False
        i += k
    return True


def validate_operation_interval(interval_h: int) -> None:
    if interval_h not in VALID_OPERATION_INTERVALS_H:
        raise ValueError(
            f"operation_interval_h={interval_h} is not supported. "
            f"Valid values: {sorted(VALID_OPERATION_INTERVALS_H)}"
        )


def _failure_row(
    event_id: str,
    specified_family: str,
    operation_interval_h: int,
    config_hash: str,
    failure_reason: str,
    season: str = "",
    flood_limit: float = float("nan"),
) -> dict[str, Any]:
    nan = float("nan")
    return {
        "result_id": str(uuid4()),
        "config_hash": config_hash,
        "event_id": event_id,
        "scenario_type": "static",
        "scenario_group": "",
        "workflow_stage": "static",
        "extension_type": EXTENSION_TYPE,
        "workflow_type": "stage1_direct_service",
        "specified_release_family": specified_family,
        "actual_release_family": "unknown",
        "command_compliance": False,
        "operation_interval_h": operation_interval_h,
        "interval_compliance": False,
        "accepted": False,
        "hard_violation": True,
        "violation_details": failure_reason,
        "failure_reason": failure_reason,
        "initial_level": nan,
        "max_level": nan,
        "terminal_level": nan,
        "terminal_deviation": nan,
        "peak_inflow": nan,
        "peak_release": nan,
        "peak_reduction_rate": nan,
        "inflow_peak_attenuation_rate": nan,
        "max_release": nan,
        "release_smoothness": nan,
        "total_inflow_volume_1e8m3": nan,
        "total_release_volume_1e8m3": nan,
        "routing_max_flow_hecheng": nan,
        "downstream_violation": False,
        "downstream_margin": nan,
        "optimization_score": nan,
        "season": season,
        "flood_limit_applied": flood_limit,
        "trigger_type": "",
        "action": "",
    }


class InstructionStaticRunner:
    """Direct-service runner for the instruction-conditioned static extension.

    Forces a specified release family, quantizes the release series to the
    specified operation interval, re-simulates, and evaluates. All metrics
    are derived from the post-quantization simulation.
    """

    def __init__(self, data_root: str = "data") -> None:
        self.spec = load_default_experiment_spec()
        self.adapter = RealEventDataAdapter(data_root=data_root)
        self.program_service = ProgramService()
        self.simulation_service = SimulationService(
            spec=self.spec,
            module_registry=dict(BASE_RELEASE_MODULE_REGISTRY),
        )
        self.optimization_service = OptimizationService(
            spec=self.spec,
            program_service=self.program_service,
        )
        self.routing_check = MuskingumDownstreamCheck()

    def run_instruction_static(
        self,
        event_id: str,
        specified_family: str,
        operation_interval_h: int,
    ) -> dict[str, Any]:
        """Run one (event, family, interval) combination.

        All metrics are computed after quantization and re-simulation.
        """
        validate_operation_interval(operation_interval_h)

        try:
            event = self.adapter.load_event(event_id)
        except Exception as exc:
            return _failure_row(
                event_id, specified_family, operation_interval_h,
                config_hash="",
                failure_reason=f"event_load_error: {exc}",
            )

        first_idx = event.first_valid_index()
        first = event.records[first_idx]
        usable = event.records[first_idx:]

        month = first.time.month
        day = first.time.day
        flood_limit = get_flood_limit(month, day)
        season = get_season_name(month, day)
        constraints = build_tankeng_constraints(month, day)
        task_constraints = {"target_level": flood_limit, "target_tolerance": 0.5}
        config_hash = make_config_hash(event_id, specified_family, operation_interval_h, constraints)

        initial_state = ReservoirState(
            timestamp=first.time,
            level=float(first.level),
            storage=float(self.spec.level_storage_curve.get_storage(float(first.level))),
            inflow=float(first.inflow),
            outflow=float(first.outflow) if first.outflow is not None else float(first.inflow),
        )
        forecast_values = [float(r.inflow) for r in usable if r.inflow is not None]
        timestamps = [r.time for r in usable[: len(forecast_values)]]
        forecast = ForecastBundle(
            forecast_time=timestamps[0],
            series=[
                ForecastSeries(
                    variable="inflow",
                    timestamps=timestamps,
                    values=forecast_values,
                    unit="m3/s",
                )
            ],
        )

        try:
            opt_result = self.optimization_service.optimize_release_plan(
                initial_state=initial_state,
                forecast=forecast,
                constraints=constraints,
                task_constraints=task_constraints,
                requested_module_type=specified_family,
                name=f"instr_static_{event_id}_{specified_family}_{operation_interval_h}h",
            )
        except ValueError as exc:
            reason = (
                "unsupported_family"
                if "supported" in str(exc).lower()
                else f"optimization_error: {exc}"
            )
            return _failure_row(
                event_id, specified_family, operation_interval_h,
                config_hash=config_hash,
                failure_reason=reason,
                season=season,
                flood_limit=flood_limit,
            )
        except Exception as exc:
            return _failure_row(
                event_id, specified_family, operation_interval_h,
                config_hash=config_hash,
                failure_reason=f"optimization_error: {exc}",
                season=season,
                flood_limit=flood_limit,
            )

        candidate = opt_result.selected_candidate
        actual_family: str | None = getattr(candidate, "module_type", None)
        if not actual_family:
            return _failure_row(
                event_id, specified_family, operation_interval_h,
                config_hash=config_hash,
                failure_reason="actual_family_unavailable",
                season=season,
                flood_limit=flood_limit,
            )

        command_compliance = actual_family == specified_family
        family_failure_reason: str | None = None if command_compliance else "family_mismatch"

        raw_release = [s.outflow for s in candidate.simulation_result.snapshots]
        time_step_h = event.time_step_hours
        k = max(1, operation_interval_h // time_step_h)
        quantized_release = quantize_to_interval(raw_release, k)
        interval_compliance = check_interval_compliance(quantized_release, k)

        try:
            re_sim_result = self._resimulate(
                initial_state=initial_state,
                inflow_series=forecast_values,
                release_series=quantized_release,
                timestamps=timestamps,
                program_id=opt_result.program.id,
            )
        except Exception as exc:
            return _failure_row(
                event_id, specified_family, operation_interval_h,
                config_hash=config_hash,
                failure_reason=f"resimulation_error: {exc}",
                season=season,
                flood_limit=flood_limit,
            )

        re_release = [s.outflow for s in re_sim_result.snapshots]
        downstream_violated, routing_max = self.routing_check.check_violation(re_release)

        peak_inflow = max((r.inflow for r in usable if r.inflow is not None), default=0.0)
        peak_level = max((s.level for s in re_sim_result.snapshots), default=0.0)
        volume = sum(float(r.inflow) for r in usable if r.inflow is not None) * 3 * 3600 / 1e8
        scenario_group = classify_event(peak_inflow, peak_level, volume)

        re_candidate = ReleaseOptimizationCandidate(
            module_type=actual_family,
            module_parameters=dict(candidate.module_parameters),
            simulation_result=re_sim_result,
            evaluation_result=candidate.evaluation_result,
            violations=candidate.violations,
            unmet_task_constraints=candidate.unmet_task_constraints,
            objective_score=candidate.objective_score,
            solve_metadata=dict(candidate.solve_metadata),
        )
        re_opt_result = ReleaseOptimizationResult(
            program=opt_result.program,
            selected_candidate=re_candidate,
            family_attempts=opt_result.family_attempts,
            requested_module_type=opt_result.requested_module_type,
            fallback_applied=opt_result.fallback_applied,
            solution_mode=opt_result.solution_mode,
        )

        base = extract_unified_metrics(
            event_id=event_id,
            scenario_type="static",
            scenario_group=scenario_group,
            opt_result=re_opt_result,
            sim_result=re_sim_result,
            routing_max_flow=routing_max,
            downstream_violation=downstream_violated,
            flood_limit=flood_limit,
            season=season,
            workflow_stage="static",
            initial_level=float(first.level),
        )

        base.update({
            "result_id": str(uuid4()),
            "config_hash": config_hash,
            "extension_type": EXTENSION_TYPE,
            "workflow_type": "stage1_direct_service",
            "specified_release_family": specified_family,
            "actual_release_family": actual_family,
            "command_compliance": command_compliance,
            "operation_interval_h": operation_interval_h,
            "interval_compliance": interval_compliance,
            "inflow_peak_attenuation_rate": base.get("peak_reduction_rate", float("nan")),
            "downstream_margin": 14000.0 - routing_max,
            "failure_reason": family_failure_reason or "",
        })

        return base

    def _resimulate(
        self,
        initial_state: ReservoirState,
        inflow_series: list[float],
        release_series: list[float],
        timestamps: list,
        program_id: str,
    ):
        """Step through water balance with a fixed release series.

        Returns a SimulationResult. All metrics are derived from this result.
        """
        from datetime import timedelta

        from pyresops.core.hydraulics import HydraulicsCalculator
        from pyresops.domain.result import SimulationResult, StateSnapshot

        hydraulics = HydraulicsCalculator(self.spec)
        dt_seconds = 3 * 3600

        n = min(len(inflow_series), len(release_series))
        snapshots: list[StateSnapshot] = []
        state = initial_state

        for i in range(n):
            inflow = inflow_series[i]
            outflow = release_series[i]
            max_q = hydraulics.compute_max_discharge(state.level)
            outflow = min(max(outflow, 0.0), max_q)

            ts = (
                timestamps[i]
                if i < len(timestamps)
                else state.timestamp + timedelta(seconds=dt_seconds * i)
            )
            snapshots.append(StateSnapshot(
                timestamp=ts,
                level=state.level,
                storage=state.storage,
                inflow=inflow,
                outflow=outflow,
                active_module=None,
            ))
            state = hydraulics.water_balance_step(state, inflow, outflow, dt_seconds)

        if not snapshots:
            raise ValueError("Re-simulation produced no snapshots")

        levels = [s.level for s in snapshots]
        outflows = [s.outflow for s in snapshots]

        return SimulationResult(
            program_id=program_id,
            start_time=snapshots[0].timestamp,
            end_time=snapshots[-1].timestamp,
            snapshots=snapshots,
            max_level=max(levels),
            min_level=min(levels),
            avg_outflow=sum(outflows) / len(outflows),
        )
