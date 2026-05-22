"""Dynamic command-intervention extension -- Stage 1 direct-service runner.

Evaluates whether PyResOps can handle operator commands issued mid-event at
specific checkpoints (T1=rising limb, T2_peak=near peak). Commands may be
physically infeasible; correct rejection counts as command_handling_success.

Matrix: 5 events x 4 command types x 2 checkpoints = 40 records.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pyresops.agents.specs import load_default_experiment_spec
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import ReservoirState
from pyresops.services import OptimizationService, ProgramService

from experiments.data_adapters.real_events import FloodEventData, RealEventDataAdapter
from experiments.stage1.checkpoints import compute_dynamic_checkpoints
from experiments.stage1.classify import classify_event
from experiments.stage1.constraints import (
    build_tankan_constraints,
    build_tankan_task_constraints,
    get_flood_limit,
    get_season_name,
)
from experiments.stage1.downstream import MuskingumDownstreamCheck
from experiments.stage1.metrics import extract_unified_metrics

EXTENSION_TYPE = "dynamic_command_intervention"

SELECTED_EVENTS: list[str] = [
    "2010062002",
    "2021052114",
    "2009080920",
    "2012062402",
    "2024061623",
]

COMMAND_TYPES: list[str] = [
    "D1_release_cap_adjustment",
    "D2_terminal_target_lowering",
    "D3_target_deadline_compression",
    "D4_conservative_risk_buffer",
]

CHECKPOINT_LABELS: list[str] = ["T1", "T2_peak"]

D1_RELEASE_CAP_M3S = 1500.0
D1_RELEASE_CAP_MODERATE_M3S = 2000.0
D1_HIGH_INFLOW_THRESHOLD_M3S = 3000.0
D2_TARGET_DELTA_M = -0.5
D3_ORIGINAL_HORIZON_H = 12
D3_NEW_DEADLINE_H = 9
D4_FLOOD_LIMIT_BUFFER_M = 0.3


@dataclass
class CheckpointState:
    event_id: str
    checkpoint_id: str
    checkpoint_hour: float
    checkpoint_idx: int
    sliced_event: FloodEventData
    initial_level: float
    flood_limit: float
    season: str
    peak_inflow: float
    constraints: dict
    task_constraints: dict


@dataclass
class CommandSpec:
    command_type: str
    command_text: str
    command_parameters: dict


def make_config_hash(
    event_id: str,
    checkpoint_id: str,
    command_type: str,
    constraints: dict,
) -> str:
    payload = (
        event_id
        + checkpoint_id
        + command_type
        + json.dumps(constraints, sort_keys=True)
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _failure_row(
    event_id: str,
    checkpoint_id: str,
    checkpoint_hour: float,
    command_type: str,
    command_text: str,
    command_parameters: dict,
    config_hash: str,
    failure_reason: str,
    season: str,
    flood_limit: float,
    command_handling_success: bool,
    feasible_execution_success: bool,
    infeasibility_reason: str,
    workflow_type: str = "stage1_direct",
) -> dict:
    nan = float("nan")
    return {
        "result_id": str(uuid4()),
        "config_hash": config_hash,
        "event_id": event_id,
        "extension_type": EXTENSION_TYPE,
        "workflow_type": workflow_type,
        "checkpoint_id": checkpoint_id,
        "checkpoint_hour": checkpoint_hour,
        "command_type": command_type,
        "command_text": command_text,
        "command_parameters": json.dumps(command_parameters),
        "accepted": command_handling_success,
        "command_handling_success": command_handling_success,
        "feasible_execution_success": feasible_execution_success,
        "infeasibility_reason": infeasibility_reason,
        "failure_reason": failure_reason,
        "season": season,
        "flood_limit_applied": flood_limit,
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
        "hard_violation": True,
        "violation_details": failure_reason,
        "trigger_type": "command_intervention",
        "action": "rejected",
        "scenario_type": "dynamic_command",
        "scenario_group": "",
        "workflow_stage": "checkpoint",
    }


def build_checkpoint_states(event: FloodEventData, spec: Any) -> list[CheckpointState]:
    """Build T1 and T2_peak checkpoint states for one event."""
    inflows = [r.inflow for r in event.records if r.inflow is not None]
    cp_indices = compute_dynamic_checkpoints(inflows, event.time_step_hours)

    label_to_cp = {
        "T1": cp_indices[1],
        "T2_peak": cp_indices[2],
    }

    states: list[CheckpointState] = []
    for label, cp_idx in label_to_cp.items():
        offset_hours = cp_idx * event.time_step_hours
        sliced = event.slice_from_hour(offset_hours)

        first_idx = sliced.first_valid_index()
        first_rec = sliced.records[first_idx]
        initial_level = first_rec.level if first_rec.level is not None else spec.initial_level

        first_event_rec = event.records[0]
        month = first_event_rec.time.month
        day = first_event_rec.time.day
        flood_limit = get_flood_limit(month, day)
        season = get_season_name(month, day)

        constraints = build_tankan_constraints(month, day)
        task_constraints = build_tankan_task_constraints(flood_limit)

        sliced_inflows = [r.inflow for r in sliced.records if r.inflow is not None]
        peak_inflow = max(sliced_inflows) if sliced_inflows else 0.0

        states.append(CheckpointState(
            event_id=event.event_id,
            checkpoint_id=label,
            checkpoint_hour=offset_hours,
            checkpoint_idx=cp_idx,
            sliced_event=sliced,
            initial_level=initial_level,
            flood_limit=flood_limit,
            season=season,
            peak_inflow=peak_inflow,
            constraints=constraints,
            task_constraints=task_constraints,
        ))

    return states


def build_command(command_type: str, cp_state: CheckpointState) -> CommandSpec:
    """Build a CommandSpec for the given command type and checkpoint state."""
    fl = cp_state.flood_limit

    if command_type == "D1_release_cap_adjustment":
        cap = (
            D1_RELEASE_CAP_M3S
            if cp_state.peak_inflow >= D1_HIGH_INFLOW_THRESHOLD_M3S
            else D1_RELEASE_CAP_MODERATE_M3S
        )
        params = {"release_cap_m3s": cap}
        text = f"Operator: cap release at {cap:.0f} m3/s for remainder of event"
        return CommandSpec(command_type=command_type, command_text=text, command_parameters=params)

    if command_type == "D2_terminal_target_lowering":
        new_target = fl + D2_TARGET_DELTA_M
        params = {"new_target_level_m": new_target, "delta_m": D2_TARGET_DELTA_M}
        text = f"Operator: lower terminal target to {new_target:.2f} m (delta={D2_TARGET_DELTA_M:+.1f} m)"
        return CommandSpec(command_type=command_type, command_text=text, command_parameters=params)

    if command_type == "D3_target_deadline_compression":
        params = {
            "original_horizon_h": D3_ORIGINAL_HORIZON_H,
            "new_deadline_h": D3_NEW_DEADLINE_H,
        }
        text = f"Operator: compress planning horizon from {D3_ORIGINAL_HORIZON_H}h to {D3_NEW_DEADLINE_H}h"
        return CommandSpec(command_type=command_type, command_text=text, command_parameters=params)

    if command_type == "D4_conservative_risk_buffer":
        buffered = fl - D4_FLOOD_LIMIT_BUFFER_M
        params = {"buffered_level_max_m": buffered, "buffer_m": D4_FLOOD_LIMIT_BUFFER_M}
        text = f"Operator: apply {D4_FLOOD_LIMIT_BUFFER_M} m safety buffer, effective ceiling {buffered:.2f} m"
        return CommandSpec(command_type=command_type, command_text=text, command_parameters=params)

    raise ValueError(f"Unknown command_type: {command_type}")


def check_d1_feasibility(cp_state: CheckpointState, release_cap: float) -> tuple[bool, str]:
    if release_cap <= 0:
        return False, f"release_cap={release_cap} <= 0"
    if release_cap < 100:
        return False, f"release_cap={release_cap} < 100 m3/s (operationally infeasible)"
    return True, ""


def check_d2_feasibility(cp_state: CheckpointState, new_target: float) -> tuple[bool, str]:
    DEAD_STORAGE_LEVEL = 130.0
    if new_target < DEAD_STORAGE_LEVEL:
        return False, f"new_target={new_target:.2f} m < dead storage {DEAD_STORAGE_LEVEL} m"
    if new_target > cp_state.flood_limit:
        return False, f"new_target={new_target:.2f} m > flood_limit={cp_state.flood_limit} m"
    return True, ""


def check_d3_feasibility(
    cp_state: CheckpointState, new_deadline_h: float, target_level: float
) -> tuple[bool, str]:
    dt = cp_state.sliced_event.time_step_hours
    deadline_steps = int(new_deadline_h / dt)
    if deadline_steps < 1:
        return False, f"new_deadline_h={new_deadline_h} yields {deadline_steps} steps (< 1)"
    return True, ""


def check_d4_feasibility(cp_state: CheckpointState, buffered_limit: float) -> tuple[bool, str]:
    if buffered_limit < cp_state.initial_level:
        return (
            False,
            f"buffered_limit={buffered_limit:.2f} m < initial_level={cp_state.initial_level:.2f} m",
        )
    return True, ""


def _make_truncated_event(event: FloodEventData, n_steps: int) -> FloodEventData:
    """Return a copy of event with records truncated to n_steps valid inflow records."""
    import dataclasses
    valid = [r for r in event.records if r.inflow is not None]
    truncated = valid[:n_steps]
    return dataclasses.replace(event, records=truncated)


def replan_with_command(
    cp_state: CheckpointState,
    command: CommandSpec,
    opt_service: OptimizationService,
    routing_check: MuskingumDownstreamCheck,
    spec: Any,
) -> tuple[bool, Any, str]:
    """Apply command constraints and run optimization. Returns (success, result, reason)."""
    sliced = cp_state.sliced_event
    dt = sliced.time_step_hours

    modified_constraints = dict(cp_state.constraints)
    modified_task_constraints = dict(cp_state.task_constraints)

    ct = command.command_type
    params = command.command_parameters

    if ct == "D1_release_cap_adjustment":
        modified_constraints["max_release"] = params["release_cap_m3s"]

    elif ct == "D2_terminal_target_lowering":
        modified_task_constraints["target_level"] = params["new_target_level_m"]

    elif ct == "D3_target_deadline_compression":
        new_deadline_h = params["new_deadline_h"]
        deadline_steps = max(1, int(new_deadline_h / dt))
        sliced = _make_truncated_event(sliced, deadline_steps)
        modified_task_constraints["max_final_level"] = cp_state.task_constraints.get(
            "target_level", cp_state.flood_limit
        )

    elif ct == "D4_conservative_risk_buffer":
        modified_constraints["level_max"] = params["buffered_level_max_m"]

    first_rec = sliced.records[sliced.first_valid_index()]
    initial_state = ReservoirState(
        timestamp=first_rec.time,
        level=float(cp_state.initial_level),
        storage=float(spec.level_storage_curve.get_storage(float(cp_state.initial_level))),
        inflow=float(first_rec.inflow) if first_rec.inflow is not None else 0.0,
        outflow=float(first_rec.outflow) if first_rec.outflow is not None else (
            float(first_rec.inflow) if first_rec.inflow is not None else 0.0
        ),
    )

    usable = [r for r in sliced.records if r.inflow is not None]
    if not usable:
        return False, None, "no inflow data in sliced event"
    inflow_values = [float(r.inflow) for r in usable]
    timestamps = [r.time for r in usable]

    forecast_series = ForecastSeries(
        variable="inflow",
        timestamps=timestamps,
        values=inflow_values,
    )
    forecast = ForecastBundle(forecast_time=timestamps[0], series=[forecast_series])

    try:
        opt_result = opt_service.optimize_release_plan(
            initial_state=initial_state,
            forecast=forecast,
            constraints=modified_constraints,
            task_constraints=modified_task_constraints,
            name=f"{cp_state.event_id}_{cp_state.checkpoint_id}_{ct}",
        )
    except Exception as exc:
        return False, None, f"optimization_exception: {exc}"

    return True, opt_result, ""


class DynamicCommandInterventionRunner:
    """Stage 1 direct-service runner for dynamic command-intervention extension."""

    EXTENSION_TYPE = EXTENSION_TYPE
    WORKFLOW_TYPE = "stage1_direct"

    def __init__(self, data_root: str = "data") -> None:
        self.spec = load_default_experiment_spec()
        self.adapter = RealEventDataAdapter(data_root=data_root)
        self.program_service = ProgramService()
        self.optimization_service = OptimizationService(
            spec=self.spec,
            program_service=self.program_service,
        )
        self.routing_check = MuskingumDownstreamCheck()

    def run_single(self, event_id: str, checkpoint_id: str, command_type: str) -> dict:
        """Run one (event, checkpoint, command) combination and return a result row."""
        try:
            event = self.adapter.load_event(event_id)
        except Exception as exc:
            config_hash = make_config_hash(event_id, checkpoint_id, command_type, {})
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=float("nan"), command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"load_event_failed: {exc}", season="",
                flood_limit=float("nan"), command_handling_success=False,
                feasible_execution_success=False, infeasibility_reason="",
                workflow_type=self.WORKFLOW_TYPE,
            )

        try:
            cp_states = build_checkpoint_states(event, self.spec)
        except Exception as exc:
            config_hash = make_config_hash(event_id, checkpoint_id, command_type, {})
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=float("nan"), command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"checkpoint_build_failed: {exc}", season="",
                flood_limit=float("nan"), command_handling_success=False,
                feasible_execution_success=False, infeasibility_reason="",
                workflow_type=self.WORKFLOW_TYPE,
            )

        cp_state = next((s for s in cp_states if s.checkpoint_id == checkpoint_id), None)
        if cp_state is None:
            config_hash = make_config_hash(event_id, checkpoint_id, command_type, {})
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=float("nan"), command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"checkpoint_not_found: {checkpoint_id}", season="",
                flood_limit=float("nan"), command_handling_success=False,
                feasible_execution_success=False, infeasibility_reason="",
                workflow_type=self.WORKFLOW_TYPE,
            )

        config_hash = make_config_hash(
            event_id, checkpoint_id, command_type, cp_state.constraints
        )

        try:
            command = build_command(command_type, cp_state)
        except Exception as exc:
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"command_build_failed: {exc}",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=False, feasible_execution_success=False,
                infeasibility_reason="", workflow_type=self.WORKFLOW_TYPE,
            )

        feasible_pre, infeasibility_reason = self._check_feasibility(command, cp_state)
        if not feasible_pre:
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text=command.command_text,
                command_parameters=command.command_parameters,
                config_hash=config_hash,
                failure_reason="command_infeasible_correctly_rejected",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=True, feasible_execution_success=False,
                infeasibility_reason=infeasibility_reason,
                workflow_type=self.WORKFLOW_TYPE,
            )

        success, opt_result, reason = replan_with_command(
            cp_state, command, self.optimization_service, self.routing_check, self.spec
        )

        if not success or opt_result is None:
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text=command.command_text,
                command_parameters=command.command_parameters,
                config_hash=config_hash,
                failure_reason=reason or "optimization_failed",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=True, feasible_execution_success=False,
                infeasibility_reason=reason, workflow_type=self.WORKFLOW_TYPE,
            )

        candidate = opt_result.selected_candidate
        if not candidate.feasible:
            return _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text=command.command_text,
                command_parameters=command.command_parameters,
                config_hash=config_hash,
                failure_reason="optimizer_returned_infeasible",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=True, feasible_execution_success=False,
                infeasibility_reason="optimizer_infeasible",
                workflow_type=self.WORKFLOW_TYPE,
            )

        release_series = [s.outflow for s in opt_result.selected_candidate.simulation_result.snapshots]
        downstream_violated, routing_max_flow = self.routing_check.check_violation(release_series)
        downstream_margin = 14000.0 - routing_max_flow

        sim_snaps = opt_result.selected_candidate.simulation_result.snapshots
        peak_inflow_val = cp_state.peak_inflow
        peak_level_val = max((s.level for s in sim_snaps), default=0.0)
        usable_records = [r for r in cp_state.sliced_event.records if r.inflow is not None]
        volume_val = sum(float(r.inflow) for r in usable_records) * cp_state.sliced_event.time_step_hours * 3600 / 1e8
        scenario_group = classify_event(peak_inflow_val, peak_level_val, volume_val)

        metrics = extract_unified_metrics(
            event_id=event_id,
            scenario_type="dynamic_command",
            scenario_group=scenario_group,
            opt_result=opt_result,
            sim_result=opt_result.selected_candidate.simulation_result,
            routing_max_flow=routing_max_flow,
            downstream_violation=downstream_violated,
            flood_limit=cp_state.flood_limit,
            season=cp_state.season,
            workflow_stage="checkpoint",
            trigger_type="command_intervention",
            action="replan",
            initial_level=cp_state.initial_level,
        )

        row = {
            "result_id": str(uuid4()),
            "config_hash": config_hash,
            "extension_type": EXTENSION_TYPE,
            "workflow_type": self.WORKFLOW_TYPE,
            "checkpoint_id": checkpoint_id,
            "checkpoint_hour": cp_state.checkpoint_hour,
            "command_type": command_type,
            "command_text": command.command_text,
            "command_parameters": json.dumps(command.command_parameters),
            "accepted": True,
            "command_handling_success": True,
            "feasible_execution_success": True,
            "infeasibility_reason": "",
            "failure_reason": "",
            "downstream_margin": round(downstream_margin, 1),
        }
        row.update(metrics)
        return row

    def _check_feasibility(
        self, command: CommandSpec, cp_state: CheckpointState
    ) -> tuple[bool, str]:
        ct = command.command_type
        params = command.command_parameters
        if ct == "D1_release_cap_adjustment":
            return check_d1_feasibility(cp_state, params["release_cap_m3s"])
        if ct == "D2_terminal_target_lowering":
            return check_d2_feasibility(cp_state, params["new_target_level_m"])
        if ct == "D3_target_deadline_compression":
            return check_d3_feasibility(
                cp_state,
                params["new_deadline_h"],
                cp_state.task_constraints.get("target_level", cp_state.flood_limit),
            )
        if ct == "D4_conservative_risk_buffer":
            return check_d4_feasibility(cp_state, params["buffered_level_max_m"])
        return False, f"unknown command type: {ct}"

    def run_all(
        self,
        events: list[str] | None = None,
        command_types: list[str] | None = None,
        checkpoint_labels: list[str] | None = None,
    ) -> list[dict]:
        """Run all combinations and return list of result rows."""
        events = events or SELECTED_EVENTS
        command_types = command_types or COMMAND_TYPES
        checkpoint_labels = checkpoint_labels or CHECKPOINT_LABELS

        results: list[dict] = []
        for event_id in events:
            for checkpoint_id in checkpoint_labels:
                for command_type in command_types:
                    row = self.run_single(event_id, checkpoint_id, command_type)
                    results.append(row)
        return results
