"""Stage 2 deterministic workflow wrappers.

Each class mirrors the semantic structure of the LLM-facing workflow classes
(prepare → optimize → simulate → evaluate → validate) but calls OptimizationService
directly, with no agent/LLM/MCP involvement.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from pyresops.agents.specs import load_default_experiment_spec
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import ReservoirState
from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
from pyresops.services import OptimizationService, ProgramService, SimulationService

from experiments.data_adapters.real_events import FloodEventData, RealEventDataAdapter
from experiments.stage1.checkpoints import compute_dynamic_checkpoints
from experiments.stage1.classify import classify_event
from experiments.stage1.constraints import (
    build_tankan_constraints,
    get_flood_limit,
    get_season_name,
)
from experiments.stage1.downstream import MuskingumDownstreamCheck
from experiments.stage1.metrics import extract_unified_metrics


# ---------------------------------------------------------------------------
# Shared infrastructure
# ---------------------------------------------------------------------------

def _build_services() -> tuple[Any, OptimizationService, MuskingumDownstreamCheck]:
    spec = load_default_experiment_spec()
    program_service = ProgramService()
    SimulationService(
        spec=spec,
        module_registry=dict(BASE_RELEASE_MODULE_REGISTRY),
    )
    opt_service = OptimizationService(spec=spec, program_service=program_service)
    routing_check = MuskingumDownstreamCheck()
    return spec, opt_service, routing_check


def _make_forecast(event: FloodEventData, use_predict: bool = False) -> tuple[ForecastBundle, list]:
    first_idx = event.first_valid_index()
    usable = event.records[first_idx:]
    if use_predict and event.has_prediction:
        values = [float(r.predict) for r in usable if r.predict is not None]
    else:
        values = [float(r.inflow) for r in usable if r.inflow is not None]
    timestamps = [r.time for r in usable[: len(values)]]
    forecast = ForecastBundle(
        forecast_time=timestamps[0],
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=timestamps,
                values=values,
                unit="m3/s",
            )
        ],
    )
    return forecast, usable


def _initial_state(spec: Any, event: FloodEventData) -> tuple[ReservoirState, Any]:
    first_idx = event.first_valid_index()
    first = event.records[first_idx]
    state = ReservoirState(
        timestamp=first.time,
        level=float(first.level),
        storage=float(spec.level_storage_curve.get_storage(float(first.level))),
        inflow=float(first.inflow),
        outflow=float(first.outflow) if first.outflow is not None else float(first.inflow),
    )
    return state, first


def _config_hash(event_id: str, workflow_stage: str, scenario_type: str) -> str:
    payload = json.dumps(
        {"event_id": event_id, "workflow_stage": workflow_stage, "scenario_type": scenario_type},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _result_id(event_id: str, workflow_stage: str) -> str:
    return f"{event_id}__{workflow_stage}"


def _run_optimization(
    spec: Any,
    opt_service: OptimizationService,
    routing_check: MuskingumDownstreamCheck,
    event: FloodEventData,
    workflow_stage: str,
    scenario_type: str,
    use_predict: bool = False,
    action: str | None = None,
    trigger_type: str | None = None,
) -> dict[str, Any]:
    """Core optimization step shared by all three workflow types."""
    initial_state, first = _initial_state(spec, event)
    forecast, usable = _make_forecast(event, use_predict=use_predict)

    month = first.time.month
    day = first.time.day
    flood_limit = get_flood_limit(month, day)
    season = get_season_name(month, day)
    constraints = build_tankan_constraints(month, day)
    task_constraints = {"target_level": flood_limit, "target_tolerance": 0.5}

    # optimize
    opt_result = opt_service.optimize_release_plan(
        initial_state=initial_state,
        forecast=forecast,
        constraints=constraints,
        task_constraints=task_constraints,
        name=f"stage2_{event.event_id}_{workflow_stage}",
    )

    # simulate (result already embedded in candidate)
    sim_result = opt_result.selected_candidate.simulation_result

    # evaluate
    release_series = [s.outflow for s in sim_result.snapshots]
    downstream_violated, routing_max = routing_check.check_violation(release_series)

    peak_inflow = max((r.inflow for r in usable if r.inflow is not None), default=0.0)
    peak_level = max((s.level for s in sim_result.snapshots), default=0.0)
    volume = sum(float(r.inflow) for r in usable if r.inflow is not None) * 3 * 3600 / 1e8
    scenario_group = classify_event(peak_inflow, peak_level, volume)

    # validate / build metrics
    row = extract_unified_metrics(
        event_id=event.event_id,
        scenario_type=scenario_type,
        scenario_group=scenario_group,
        opt_result=opt_result,
        sim_result=sim_result,
        routing_max_flow=routing_max,
        downstream_violation=downstream_violated,
        flood_limit=flood_limit,
        season=season,
        workflow_stage=workflow_stage,
        trigger_type=trigger_type,
        action=action,
        initial_level=float(first.level),
    )
    row["result_id"] = _result_id(event.event_id, workflow_stage)
    row["config_hash"] = _config_hash(event.event_id, workflow_stage, scenario_type)
    return row


# ---------------------------------------------------------------------------
# StaticWorkflow
# ---------------------------------------------------------------------------

class StaticWorkflow:
    """Static workflow: one full-horizon optimization per event.

    Steps: prepare → optimize → simulate → evaluate → validate
    """

    def __init__(
        self,
        adapter: RealEventDataAdapter | None = None,
        data_root: str = "data",
    ) -> None:
        self.adapter = adapter or RealEventDataAdapter(data_root=data_root)
        self._spec, self._opt, self._routing = _build_services()

    # -- step methods --------------------------------------------------------

    def prepare(self, event_id: str) -> FloodEventData:
        return self.adapter.load_event(event_id)

    def optimize(self, event: FloodEventData) -> dict[str, Any]:
        return _run_optimization(
            self._spec, self._opt, self._routing,
            event=event,
            workflow_stage="static",
            scenario_type="static",
            action="replan",
            trigger_type="initial",
        )

    def simulate(self, row: dict[str, Any]) -> dict[str, Any]:
        # simulation is embedded inside optimize; this step is a pass-through
        return row

    def evaluate(self, row: dict[str, Any]) -> dict[str, Any]:
        return row

    def validate(self, row: dict[str, Any]) -> dict[str, Any]:
        return row

    # -- orchestrator --------------------------------------------------------

    def run(self, event_id: str) -> dict[str, Any]:
        event = self.prepare(event_id)
        row = self.optimize(event)
        row = self.simulate(row)
        row = self.evaluate(row)
        return self.validate(row)


# ---------------------------------------------------------------------------
# DynamicWorkflow
# ---------------------------------------------------------------------------

class DynamicWorkflow:
    """Dynamic workflow: adaptive checkpoints with retain/replan decisions.

    Steps per checkpoint: prepare_slice → optimize_or_retain → simulate → evaluate → validate
    """

    def __init__(
        self,
        adapter: RealEventDataAdapter | None = None,
        data_root: str = "data",
    ) -> None:
        self.adapter = adapter or RealEventDataAdapter(data_root=data_root)
        self._spec, self._opt, self._routing = _build_services()

    def _should_retain(self, current_plan: dict[str, Any]) -> tuple[bool, str]:
        if current_plan.get("hard_violation"):
            return False, "prior_violation"
        if current_plan.get("terminal_deviation", 999.0) > 0.5:
            return False, "terminal_deviation_exceeded"
        return True, "plan_still_feasible"

    def prepare(self, event_id: str) -> FloodEventData:
        return self.adapter.load_event(event_id)

    def run(self, event_id: str) -> list[dict[str, Any]]:
        event = self.prepare(event_id)
        inflows = [r.inflow for r in event.records if r.inflow is not None]
        checkpoints = compute_dynamic_checkpoints(inflows, event.time_step_hours)

        results: list[dict[str, Any]] = []
        current_plan: dict[str, Any] | None = None

        for stage_num, cp_idx in enumerate(checkpoints):
            stage_label = f"T{stage_num}"
            sliced = event.slice_from_hour(cp_idx * event.time_step_hours)

            if current_plan is not None:
                retain, reason = self._should_retain(current_plan)
                if retain:
                    row = dict(current_plan)
                    row["workflow_stage"] = stage_label
                    row["action"] = "retain"
                    row["trigger_type"] = reason
                    row["result_id"] = _result_id(event.event_id, stage_label)
                    row["config_hash"] = _config_hash(event.event_id, stage_label, "dynamic")
                    results.append(row)
                    continue

            row = _run_optimization(
                self._spec, self._opt, self._routing,
                event=sliced,
                workflow_stage=stage_label,
                scenario_type="dynamic",
                action="replan",
                trigger_type="initial" if stage_num == 0 else "infeasible_or_deviation",
            )
            current_plan = row
            results.append(row)

        return results


# ---------------------------------------------------------------------------
# RollingWorkflow
# ---------------------------------------------------------------------------

@dataclass
class RollingThresholds:
    relative_error_trigger: float = 0.20
    absolute_error_trigger_m3s: float = 200.0
    level_risk_margin_m: float = 1.0
    scheduled_interval_hours: int = 12
    check_interval_hours: int = 3
    min_remaining_horizon_hours: int = 9


class RollingWorkflow:
    """Rolling workflow: 3h checks with forecast-error and level-risk triggers.

    Steps per check: observe_state → evaluate_trigger → optimize_or_retain → simulate → evaluate → validate
    """

    def __init__(
        self,
        adapter: RealEventDataAdapter | None = None,
        data_root: str = "data",
        thresholds: RollingThresholds | None = None,
    ) -> None:
        self.adapter = adapter or RealEventDataAdapter(data_root=data_root)
        self._spec, self._opt, self._routing = _build_services()
        self.thresholds = thresholds or RollingThresholds()

    def _rolling_trigger(
        self,
        offset_hours: int,
        level: float,
        inflow: float,
        predict: float,
        flood_limit: float,
    ) -> tuple[bool, str]:
        t = self.thresholds
        abs_error = abs(inflow - predict)
        rel_error = abs_error / max(abs(predict), 1.0)

        if offset_hours == 0:
            return True, "initial"
        if abs_error >= t.absolute_error_trigger_m3s:
            return True, "absolute_forecast_error"
        if rel_error >= t.relative_error_trigger:
            return True, "relative_forecast_error"
        if level >= flood_limit - t.level_risk_margin_m:
            return True, "level_risk"
        if t.scheduled_interval_hours > 0 and offset_hours % t.scheduled_interval_hours == 0:
            return True, "scheduled_check"
        return False, "retain_plan"

    def prepare(self, event_id: str) -> FloodEventData:
        withpred_path = self.adapter.data_root / "withpred" / f"{event_id}.csv"
        return self.adapter.load_predicted_event(withpred_path)

    def run(self, event_id: str) -> list[dict[str, Any]]:
        event = self.prepare(event_id)
        if not event.has_prediction:
            raise ValueError(f"{event_id}: rolling workflow requires predict column")

        t = self.thresholds
        results: list[dict[str, Any]] = []
        current_plan: dict[str, Any] | None = None

        for idx, record in enumerate(event.records):
            if record.inflow is None or record.predict is None or record.level is None:
                continue
            offset_hours = idx * event.time_step_hours
            if offset_hours % t.check_interval_hours != 0:
                continue
            remaining = event.duration_hours - offset_hours
            if remaining < t.min_remaining_horizon_hours:
                continue

            flood_limit = get_flood_limit(record.time.month, record.time.day)
            trigger, reason = self._rolling_trigger(
                offset_hours=offset_hours,
                level=record.level,
                inflow=record.inflow,
                predict=record.predict,
                flood_limit=flood_limit,
            )
            stage_label = f"rolling_{offset_hours}h"

            if not trigger and current_plan is not None:
                row = dict(current_plan)
                row["workflow_stage"] = stage_label
                row["action"] = "retain"
                row["trigger_type"] = reason
                row["result_id"] = _result_id(event.event_id, stage_label)
                row["config_hash"] = _config_hash(event.event_id, stage_label, "rolling")
                results.append(row)
                continue

            sliced = event.slice_from_hour(offset_hours)
            row = _run_optimization(
                self._spec, self._opt, self._routing,
                event=sliced,
                workflow_stage=stage_label,
                scenario_type="rolling",
                use_predict=True,
                action="replan",
                trigger_type=reason,
            )
            current_plan = row
            results.append(row)

        return results
