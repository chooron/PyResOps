"""Stage1Runner: direct PyResOps optimization without LLM/agent layer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
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
    build_tankan_task_constraints,
    get_flood_limit,
    get_season_name,
)
from experiments.stage1.downstream import MuskingumDownstreamCheck
from experiments.stage1.metrics import extract_unified_metrics


class Stage1Runner:
    """Direct PyResOps optimization without LLM/agent layer.

    Bypasses the agent/workflow/tool-chain layer entirely.
    Calls OptimizationService, SimulationService directly.
    This simulates 'an engineer using the library programmatically'.
    """

    def __init__(
        self,
        data_root: str | Path = "data",
        rolling_thresholds: dict[str, Any] | None = None,
    ) -> None:
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
        self.rolling_thresholds = rolling_thresholds or {
            "relative_error_trigger": 0.20,
            "absolute_error_trigger_m3s": 200.0,
            "level_risk_margin_m": 1.0,
            "scheduled_interval_hours": 12,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_static(self, event_id: str) -> dict[str, Any]:
        """Run one static event: full observed inflow → optimize → evaluate."""
        event = self.adapter.load_event(event_id)
        return self._run_single_stage(event, workflow_stage="static")

    def run_dynamic(self, event_id: str) -> list[dict[str, Any]]:
        """Run one event with adaptive checkpoints; retain or replan at each."""
        event = self.adapter.load_event(event_id)
        inflows = [r.inflow for r in event.records if r.inflow is not None]
        checkpoints = compute_dynamic_checkpoints(inflows, event.time_step_hours)

        results: list[dict[str, Any]] = []
        current_plan: dict[str, Any] | None = None

        for stage_num, cp_idx in enumerate(checkpoints):
            sliced = event.slice_from_hour(cp_idx * event.time_step_hours)
            stage_label = f"T{stage_num}"

            if current_plan is not None:
                retain, reason = self._should_retain(sliced, current_plan)
                if retain:
                    row = dict(current_plan)
                    row["workflow_stage"] = stage_label
                    row["action"] = "retain"
                    row["trigger_type"] = reason
                    results.append(row)
                    continue

            row = self._run_single_stage(sliced, workflow_stage=stage_label)
            row["action"] = "replan"
            row["trigger_type"] = "initial" if stage_num == 0 else "infeasible_or_deviation"
            current_plan = row
            results.append(row)

        return results

    def run_rolling(self, event_id: str) -> list[dict[str, Any]]:
        """Run one withpred event with rolling forecast-error triggers."""
        withpred_path = self.adapter.data_root / "withpred" / f"{event_id}.csv"
        event = self.adapter.load_predicted_event(withpred_path)
        if not event.has_prediction:
            raise ValueError(f"{event_id}: rolling workflow requires predict column")

        check_interval = 3  # hours
        min_remaining = 9   # hours
        results: list[dict[str, Any]] = []
        current_plan: dict[str, Any] | None = None

        for idx, record in enumerate(event.records):
            if record.inflow is None or record.predict is None or record.level is None:
                continue
            offset_hours = idx * event.time_step_hours
            if offset_hours % check_interval != 0:
                continue
            remaining = event.duration_hours - offset_hours
            if remaining < min_remaining:
                continue

            trigger, reason = self._rolling_trigger(
                offset_hours=offset_hours,
                level=record.level,
                inflow=record.inflow,
                predict=record.predict,
                flood_limit=get_flood_limit(record.time.month, record.time.day),
            )

            if not trigger and current_plan is not None:
                row = dict(current_plan)
                row["workflow_stage"] = f"rolling_{offset_hours}h"
                row["action"] = "retain"
                row["trigger_type"] = reason
                results.append(row)
                continue

            sliced = event.slice_from_hour(offset_hours)
            row = self._run_single_stage(
                sliced,
                workflow_stage=f"rolling_{offset_hours}h",
                use_predict_as_forecast=True,
            )
            row["action"] = "replan"
            row["trigger_type"] = reason
            current_plan = row
            results.append(row)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_single_stage(
        self,
        event: FloodEventData,
        workflow_stage: str = "static",
        use_predict_as_forecast: bool = False,
    ) -> dict[str, Any]:
        first_idx = event.first_valid_index()
        first = event.records[first_idx]
        usable = event.records[first_idx:]

        initial_state = ReservoirState(
            timestamp=first.time,
            level=float(first.level),
            storage=float(self.spec.level_storage_curve.get_storage(float(first.level))),
            inflow=float(first.inflow),
            outflow=float(first.outflow) if first.outflow is not None else float(first.inflow),
        )

        if use_predict_as_forecast and event.has_prediction:
            forecast_values = [
                float(r.predict) for r in usable if r.predict is not None
            ]
        else:
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

        month = first.time.month
        day = first.time.day
        flood_limit = get_flood_limit(month, day)
        season = get_season_name(month, day)
        constraints = build_tankan_constraints(month, day)
        # Target: flood limit level. Violation only if final_level > flood_limit + 0.5m.
        # Scoring minimises abs(final_level - flood_limit), so optimizer releases water
        # when inflow would push level above flood_limit, and retains storage otherwise.
        task_constraints = {
            "target_level": flood_limit,
            "target_tolerance": 0.5,
        }

        opt_result = self.optimization_service.optimize_release_plan(
            initial_state=initial_state,
            forecast=forecast,
            constraints=constraints,
            task_constraints=task_constraints,
            name=f"stage1_{event.event_id}_{workflow_stage}",
        )

        sim_result = opt_result.selected_candidate.simulation_result
        release_series = [s.outflow for s in sim_result.snapshots]
        downstream_violated, routing_max = self.routing_check.check_violation(release_series)

        peak_inflow = max((r.inflow for r in usable if r.inflow is not None), default=0.0)
        peak_level = max((s.level for s in sim_result.snapshots), default=0.0)
        volume = sum(
            float(r.inflow) for r in usable if r.inflow is not None
        ) * 3 * 3600 / 1e8

        scenario_group = classify_event(peak_inflow, peak_level, volume)

        return extract_unified_metrics(
            event_id=event.event_id,
            scenario_type=workflow_stage.split("_")[0] if "_" in workflow_stage else workflow_stage,
            scenario_group=scenario_group,
            opt_result=opt_result,
            sim_result=sim_result,
            routing_max_flow=routing_max,
            downstream_violation=downstream_violated,
            flood_limit=flood_limit,
            season=season,
            workflow_stage=workflow_stage,
            initial_level=float(first.level),
        )

    def _should_retain(
        self,
        sliced: FloodEventData,
        current_plan: dict[str, Any],
    ) -> tuple[bool, str]:
        """Return (retain, reason). Retain if plan is still feasible and terminal deviation < 0.5m."""
        if current_plan.get("hard_violation"):
            return False, "prior_violation"
        terminal_dev = current_plan.get("terminal_deviation", 999.0)
        if terminal_dev > 0.5:
            return False, "terminal_deviation_exceeded"
        return True, "plan_still_feasible"

    def _rolling_trigger(
        self,
        offset_hours: int,
        level: float,
        inflow: float,
        predict: float,
        flood_limit: float,
    ) -> tuple[bool, str]:
        """Return (trigger, reason) for rolling replan decision."""
        thresholds = self.rolling_thresholds
        abs_error = abs(inflow - predict)
        rel_error = abs_error / max(abs(predict), 1.0)

        if offset_hours == 0:
            return True, "initial"

        if abs_error >= float(thresholds.get("absolute_error_trigger_m3s", 200.0)):
            return True, "absolute_forecast_error"
        if rel_error >= float(thresholds.get("relative_error_trigger", 0.20)):
            return True, "relative_forecast_error"
        if level >= flood_limit - float(thresholds.get("level_risk_margin_m", 1.0)):
            return True, "level_risk"

        scheduled = int(thresholds.get("scheduled_interval_hours", 12))
        if scheduled > 0 and offset_hours % scheduled == 0:
            return True, "scheduled_check"

        return False, "retain_plan"
