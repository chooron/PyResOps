"""Stage 2 dynamic command-intervention workflow.

DynamicCommandInterventionWorkflow: replicates Stage 1 logic with workflow-style
step logging. Compared against Stage 1 oracle via DynamicCommandInterventionComparator.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from pyresops.agents.specs import load_default_experiment_spec
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import ReservoirState
from pyresops.services import OptimizationService, ProgramService

from experiments.data_adapters.real_events import FloodEventData, RealEventDataAdapter
from experiments.stage1.classify import classify_event
from experiments.stage1.downstream import MuskingumDownstreamCheck
from experiments.stage1.dynamic_command_intervention import (
    EXTENSION_TYPE,
    SELECTED_EVENTS,
    COMMAND_TYPES,
    CHECKPOINT_LABELS,
    CheckpointState,
    CommandSpec,
    make_config_hash,
    _failure_row,
    build_checkpoint_states,
    build_command,
    check_d1_feasibility,
    check_d2_feasibility,
    check_d3_feasibility,
    check_d4_feasibility,
    _make_truncated_event,
)
from experiments.stage1.metrics import extract_unified_metrics

_ALIGN_KEYS = ["event_id", "checkpoint_id", "command_type"]
_TOL_MAX_LEVEL = 0.5
_TOL_TERMINAL_DEV = 0.5
_TOL_PEAK_ATTENUATION = 0.05


class DynamicCommandInterventionWorkflow:
    """Workflow-style Stage 2 runner for dynamic command-intervention extension."""

    EXTENSION_TYPE = EXTENSION_TYPE
    WORKFLOW_TYPE = "stage2_workflow"

    def __init__(self, data_root: str = "data") -> None:
        self.spec = load_default_experiment_spec()
        self.adapter = RealEventDataAdapter(data_root=data_root)
        self.program_service = ProgramService()
        self.optimization_service = OptimizationService(
            spec=self.spec,
            program_service=self.program_service,
        )
        self.routing_check = MuskingumDownstreamCheck()

    def run(self, event_id: str, checkpoint_id: str, command_type: str) -> dict:
        """Execute one (event, checkpoint, command) with workflow-style step logging."""
        trace: list[dict] = []

        def _step(name: str, status: str, detail: str = "") -> None:
            trace.append({"step": name, "status": status, "detail": detail,
                          "ts": datetime.now().isoformat()})

        try:
            event = self.adapter.load_event(event_id)
            _step("load_event", "ok", event_id)
        except Exception as exc:
            _step("load_event", "error", str(exc))
            config_hash = make_config_hash(event_id, checkpoint_id, command_type, {})
            row = _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=float("nan"), command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"load_event_failed: {exc}", season="",
                flood_limit=float("nan"), command_handling_success=False,
                feasible_execution_success=False, infeasibility_reason="",
                workflow_type=self.WORKFLOW_TYPE,
            )
            row["tool_trace"] = json.dumps(trace)
            return row

        try:
            cp_states = build_checkpoint_states(event, self.spec)
            _step("build_checkpoints", "ok", f"count={len(cp_states)}")
        except Exception as exc:
            _step("build_checkpoints", "error", str(exc))
            config_hash = make_config_hash(event_id, checkpoint_id, command_type, {})
            row = _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=float("nan"), command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"checkpoint_build_failed: {exc}", season="",
                flood_limit=float("nan"), command_handling_success=False,
                feasible_execution_success=False, infeasibility_reason="",
                workflow_type=self.WORKFLOW_TYPE,
            )
            row["tool_trace"] = json.dumps(trace)
            return row

        cp_state = next((s for s in cp_states if s.checkpoint_id == checkpoint_id), None)
        if cp_state is None:
            _step("select_checkpoint", "error", f"not found: {checkpoint_id}")
            config_hash = make_config_hash(event_id, checkpoint_id, command_type, {})
            row = _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=float("nan"), command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"checkpoint_not_found: {checkpoint_id}", season="",
                flood_limit=float("nan"), command_handling_success=False,
                feasible_execution_success=False, infeasibility_reason="",
                workflow_type=self.WORKFLOW_TYPE,
            )
            row["tool_trace"] = json.dumps(trace)
            return row

        _step("select_checkpoint", "ok", f"{checkpoint_id} at hour={cp_state.checkpoint_hour}")
        config_hash = make_config_hash(
            event_id, checkpoint_id, command_type, cp_state.constraints
        )

        try:
            command = build_command(command_type, cp_state)
            _step("build_command", "ok", command.command_text)
        except Exception as exc:
            _step("build_command", "error", str(exc))
            row = _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text="", command_parameters={}, config_hash=config_hash,
                failure_reason=f"command_build_failed: {exc}",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=False, feasible_execution_success=False,
                infeasibility_reason="", workflow_type=self.WORKFLOW_TYPE,
            )
            row["tool_trace"] = json.dumps(trace)
            return row

        feasible_pre, infeasibility_reason = self._check_feasibility(command, cp_state)
        if not feasible_pre:
            _step("feasibility_check", "rejected", infeasibility_reason)
            row = _failure_row(
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
            row["tool_trace"] = json.dumps(trace)
            return row

        _step("feasibility_check", "ok", "feasible")

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

        _step("apply_command_constraints", "ok", f"ct={ct}")

        first_rec = sliced.records[sliced.first_valid_index()]
        initial_state = ReservoirState(
            timestamp=first_rec.time,
            level=float(cp_state.initial_level),
            storage=float(self.spec.level_storage_curve.get_storage(float(cp_state.initial_level))),
            inflow=float(first_rec.inflow) if first_rec.inflow is not None else 0.0,
            outflow=float(first_rec.outflow) if first_rec.outflow is not None else (
                float(first_rec.inflow) if first_rec.inflow is not None else 0.0
            ),
        )
        usable = [r for r in sliced.records if r.inflow is not None]
        if not usable:
            _step("build_forecast", "error", "no inflow data")
            row = _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text=command.command_text,
                command_parameters=command.command_parameters,
                config_hash=config_hash,
                failure_reason="no_inflow_data",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=True, feasible_execution_success=False,
                infeasibility_reason="no_inflow_data", workflow_type=self.WORKFLOW_TYPE,
            )
            row["tool_trace"] = json.dumps(trace)
            return row

        inflow_values = [float(r.inflow) for r in usable]
        timestamps = [r.time for r in usable]
        forecast_series = ForecastSeries(variable="inflow", timestamps=timestamps, values=inflow_values)
        forecast = ForecastBundle(forecast_time=timestamps[0], series=[forecast_series])
        _step("build_forecast", "ok", f"steps={len(inflow_values)}")

        try:
            opt_result = self.optimization_service.optimize_release_plan(
                initial_state=initial_state,
                forecast=forecast,
                constraints=modified_constraints,
                task_constraints=modified_task_constraints,
                name=f"{event_id}_{checkpoint_id}_{ct}_s2",
            )
            _step("optimize", "ok", f"feasible={opt_result.selected_candidate.feasible}")
        except Exception as exc:
            _step("optimize", "error", str(exc))
            row = _failure_row(
                event_id=event_id, checkpoint_id=checkpoint_id,
                checkpoint_hour=cp_state.checkpoint_hour, command_type=command_type,
                command_text=command.command_text,
                command_parameters=command.command_parameters,
                config_hash=config_hash,
                failure_reason=f"optimization_exception: {exc}",
                season=cp_state.season, flood_limit=cp_state.flood_limit,
                command_handling_success=True, feasible_execution_success=False,
                infeasibility_reason=f"optimization_exception: {exc}",
                workflow_type=self.WORKFLOW_TYPE,
            )
            row["tool_trace"] = json.dumps(trace)
            return row

        candidate = opt_result.selected_candidate
        if not candidate.feasible:
            _step("feasibility_result", "infeasible")
            row = _failure_row(
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
            row["tool_trace"] = json.dumps(trace)
            return row

        _step("feasibility_result", "ok", "feasible")
        release_series = [s.outflow for s in opt_result.selected_candidate.simulation_result.snapshots]
        downstream_violated, routing_max_flow = self.routing_check.check_violation(release_series)
        downstream_margin = 14000.0 - routing_max_flow
        _step("downstream_routing", "ok", f"max_flow={routing_max_flow:.1f}")

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
        _step("extract_metrics", "ok")

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
            "tool_trace": json.dumps(trace),
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
        events = events or SELECTED_EVENTS
        command_types = command_types or COMMAND_TYPES
        checkpoint_labels = checkpoint_labels or CHECKPOINT_LABELS
        results: list[dict] = []
        for event_id in events:
            for checkpoint_id in checkpoint_labels:
                for command_type in command_types:
                    row = self.run(event_id, checkpoint_id, command_type)
                    results.append(row)
        return results


class DynamicCommandInterventionComparator:
    """Aligns Stage 2 results against Stage 1 oracle and reports discrepancies."""

    def __init__(
        self,
        oracle_dir: str | Path,
        tol_max_level: float = _TOL_MAX_LEVEL,
        tol_terminal_dev: float = _TOL_TERMINAL_DEV,
        tol_peak_attenuation: float = _TOL_PEAK_ATTENUATION,
    ) -> None:
        self.oracle_dir = Path(oracle_dir)
        self.tol_max_level = tol_max_level
        self.tol_terminal_dev = tol_terminal_dev
        self.tol_peak_attenuation = tol_peak_attenuation

    def load_oracle(self) -> pd.DataFrame:
        parquet = self.oracle_dir / "results.parquet"
        csv = self.oracle_dir / "results.csv"
        if parquet.exists():
            return pd.read_parquet(parquet)
        if csv.exists():
            return pd.read_csv(csv)
        raise FileNotFoundError(f"No oracle results found in {self.oracle_dir}")

    def compare(self, stage2_results: list[dict]) -> pd.DataFrame:
        """Align stage2 results against oracle and return comparison DataFrame."""
        oracle_df = self.load_oracle()
        s2_df = pd.DataFrame(stage2_results)

        oracle_df = _coerce_align_keys(oracle_df)
        s2_df = _coerce_align_keys(s2_df)
        merged = s2_df.merge(
            oracle_df,
            on=_ALIGN_KEYS,
            suffixes=("_s2", "_s1"),
            how="left",
        )

        rows = []
        for _, row in merged.iterrows():
            rec = {k: row[k] for k in _ALIGN_KEYS}
            rec["s2_command_handling_success"] = row.get("command_handling_success_s2")
            rec["s1_command_handling_success"] = row.get("command_handling_success_s1")
            rec["s2_feasible_execution_success"] = row.get("feasible_execution_success_s2")
            rec["s1_feasible_execution_success"] = row.get("feasible_execution_success_s1")

            handling_match = (
                rec["s2_command_handling_success"] == rec["s1_command_handling_success"]
            )
            execution_match = (
                rec["s2_feasible_execution_success"] == rec["s1_feasible_execution_success"]
            )

            max_level_ok = True
            terminal_dev_ok = True
            attenuation_ok = True

            if rec["s1_feasible_execution_success"] and rec["s2_feasible_execution_success"]:
                s1_max = row.get("max_level_s1", float("nan"))
                s2_max = row.get("max_level_s2", float("nan"))
                if s1_max == s1_max and s2_max == s2_max:
                    max_level_ok = abs(s2_max - s1_max) <= self.tol_max_level

                s1_td = row.get("terminal_deviation_s1", float("nan"))
                s2_td = row.get("terminal_deviation_s2", float("nan"))
                if s1_td == s1_td and s2_td == s2_td:
                    terminal_dev_ok = abs(s2_td - s1_td) <= self.tol_terminal_dev

                s1_pa = row.get("inflow_peak_attenuation_rate_s1", float("nan"))
                s2_pa = row.get("inflow_peak_attenuation_rate_s2", float("nan"))
                if s1_pa == s1_pa and s2_pa == s2_pa:
                    attenuation_ok = abs(s2_pa - s1_pa) <= self.tol_peak_attenuation

            rec["handling_match"] = handling_match
            rec["execution_match"] = execution_match
            rec["max_level_within_tol"] = max_level_ok
            rec["terminal_dev_within_tol"] = terminal_dev_ok
            rec["attenuation_within_tol"] = attenuation_ok
            rec["passes_oracle"] = (
                handling_match
                and execution_match
                and max_level_ok
                and terminal_dev_ok
                and attenuation_ok
            )
            rows.append(rec)

        return pd.DataFrame(rows)


def _coerce_align_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure alignment key columns are string dtype to avoid merge type errors."""
    for col in _ALIGN_KEYS:
        if col in df.columns:
            df = df.copy()
            df[col] = df[col].astype(str)
    return df
