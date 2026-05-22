"""Stage 2 instruction-conditioned static extension.

InstructionStaticWorkflow: executes workflow-style steps directly (load →
constrain → optimize → quantize → re-simulate → route → evaluate) with
workflow-style logging. Does NOT delegate to InstructionStaticRunner.

InstructionStaticComparator: aligns Stage 2 results against Stage 1 extension
oracle and reports discrepancies.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from pyresops.agents.specs import load_default_experiment_spec
from pyresops.core.hydraulics import HydraulicsCalculator
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import ReservoirState
from pyresops.domain.result import SimulationResult, StateSnapshot
from pyresops.modules import BASE_RELEASE_MODULE_REGISTRY
from pyresops.services import OptimizationService, ProgramService, SimulationService
from pyresops.services.optimization import (
    ReleaseOptimizationCandidate,
    ReleaseOptimizationResult,
)

from experiments.data_adapters.real_events import RealEventDataAdapter
from experiments.stage1.classify import classify_event
from experiments.stage1.constraints import (
    get_flood_limit,
    get_season_name,
)
from experiments.stage1.downstream import MuskingumDownstreamCheck
from experiments.stage1.instruction_static import (
    EXTENSION_TYPE,
    build_tankeng_constraints,
    check_interval_compliance,
    make_config_hash,
    quantize_to_interval,
    validate_operation_interval,
    _failure_row,
)
from experiments.stage1.metrics import extract_unified_metrics


_ALIGN_KEYS = ["event_id", "specified_release_family", "operation_interval_h"]
_TOL_MAX_LEVEL = 0.5
_TOL_TERMINAL_DEV = 0.5
_TOL_PEAK_REDUCTION = 0.05


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class InstructionStaticWorkflow:
    """Workflow-style execution of the instruction-conditioned static extension.

    Mirrors the semantic step structure (prepare → optimize → quantize →
    re-simulate → route → evaluate) with per-step logging. Calls the service
    layer directly; does not delegate to InstructionStaticRunner.
    """

    def __init__(self, data_root: str = "data") -> None:
        self.spec = load_default_experiment_spec()
        self.adapter = RealEventDataAdapter(data_root=data_root)
        self.program_service = ProgramService()
        self.optimization_service = OptimizationService(
            spec=self.spec,
            program_service=self.program_service,
        )
        self.routing_check = MuskingumDownstreamCheck()
        self.hydraulics = HydraulicsCalculator(self.spec)

    def run(
        self,
        event_id: str,
        specified_family: str,
        operation_interval_h: int,
    ) -> dict[str, Any]:
        """Execute one (event, family, interval) combination with workflow logging."""
        validate_operation_interval(operation_interval_h)
        trace: list[dict[str, Any]] = []

        def _step(name: str, status: str, detail: str = "") -> None:
            trace.append({"step": name, "status": status, "detail": detail, "ts": datetime.now().isoformat()})

        # Step 1: load event
        try:
            event = self.adapter.load_event(event_id)
            _step("load_event", "ok", event_id)
        except Exception as exc:
            _step("load_event", "error", str(exc))
            row = _failure_row(event_id, specified_family, operation_interval_h, "", f"event_load_error: {exc}")
            row["workflow_type"] = "stage2_workflow"
            row["tool_trace"] = json.dumps(trace)
            return row

        first_idx = event.first_valid_index()
        first = event.records[first_idx]
        usable = event.records[first_idx:]

        month, day = first.time.month, first.time.day
        flood_limit = get_flood_limit(month, day)
        season = get_season_name(month, day)

        # Step 2: build Tankeng constraints
        constraints = build_tankeng_constraints(month, day)
        task_constraints = {"target_level": flood_limit, "target_tolerance": 0.5}
        config_hash = make_config_hash(event_id, specified_family, operation_interval_h, constraints)
        _step("build_constraints", "ok", f"flood_limit={flood_limit}")

        # Step 3: build initial state and forecast
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
            series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=forecast_values, unit="m3/s")],
        )
        _step("build_forecast", "ok", f"steps={len(forecast_values)}")

        # Step 4: optimize with forced family
        try:
            opt_result = self.optimization_service.optimize_release_plan(
                initial_state=initial_state,
                forecast=forecast,
                constraints=constraints,
                task_constraints=task_constraints,
                requested_module_type=specified_family,
                name=f"s2_instr_{event_id}_{specified_family}_{operation_interval_h}h",
            )
            _step("optimize", "ok", f"family={specified_family}")
        except ValueError as exc:
            reason = "unsupported_family" if "supported" in str(exc).lower() else f"optimization_error: {exc}"
            _step("optimize", "error", reason)
            row = _failure_row(event_id, specified_family, operation_interval_h, config_hash, reason, season, flood_limit)
            row["workflow_type"] = "stage2_workflow"
            row["tool_trace"] = json.dumps(trace)
            return row
        except Exception as exc:
            _step("optimize", "error", str(exc))
            row = _failure_row(event_id, specified_family, operation_interval_h, config_hash, f"optimization_error: {exc}", season, flood_limit)
            row["workflow_type"] = "stage2_workflow"
            row["tool_trace"] = json.dumps(trace)
            return row

        # Step 5: extract actual_release_family robustly
        candidate = opt_result.selected_candidate
        actual_family: str | None = getattr(candidate, "module_type", None)
        if not actual_family:
            _step("extract_family", "error", "actual_family_unavailable")
            row = _failure_row(event_id, specified_family, operation_interval_h, config_hash, "actual_family_unavailable", season, flood_limit)
            row["workflow_type"] = "stage2_workflow"
            row["tool_trace"] = json.dumps(trace)
            return row

        command_compliance = actual_family == specified_family
        family_failure_reason: str | None = None if command_compliance else "family_mismatch"
        _step("extract_family", "ok", f"actual={actual_family} compliant={command_compliance}")

        # Step 6: quantize to operation interval
        raw_release = [s.outflow for s in candidate.simulation_result.snapshots]
        k = max(1, operation_interval_h // event.time_step_hours)
        quantized_release = quantize_to_interval(raw_release, k)
        interval_compliance = check_interval_compliance(quantized_release, k)
        _step("quantize", "ok", f"k={k} interval_compliance={interval_compliance}")

        # Step 7: re-simulate with quantized release
        try:
            re_sim_result = self._resimulate(
                initial_state=initial_state,
                inflow_series=forecast_values,
                release_series=quantized_release,
                timestamps=timestamps,
                program_id=opt_result.program.id,
            )
            _step("resimulate", "ok", f"snapshots={len(re_sim_result.snapshots)}")
        except Exception as exc:
            _step("resimulate", "error", str(exc))
            row = _failure_row(event_id, specified_family, operation_interval_h, config_hash, f"resimulation_error: {exc}", season, flood_limit)
            row["workflow_type"] = "stage2_workflow"
            row["tool_trace"] = json.dumps(trace)
            return row

        # Step 8: downstream routing
        re_release = [s.outflow for s in re_sim_result.snapshots]
        downstream_violated, routing_max = self.routing_check.check_violation(re_release)
        _step("route", "ok", f"max_flow={routing_max:.1f} violated={downstream_violated}")

        # Step 9: evaluate
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
        _step("evaluate", "ok", f"accepted={base.get('accepted')}")

        base.update({
            "result_id": str(uuid4()),
            "config_hash": config_hash,
            "extension_type": EXTENSION_TYPE,
            "workflow_type": "stage2_workflow",
            "specified_release_family": specified_family,
            "actual_release_family": actual_family,
            "command_compliance": command_compliance,
            "operation_interval_h": operation_interval_h,
            "interval_compliance": interval_compliance,
            "inflow_peak_attenuation_rate": base.get("peak_reduction_rate", float("nan")),
            "downstream_margin": 14000.0 - routing_max,
            "failure_reason": family_failure_reason or "",
            "tool_trace": json.dumps(trace),
        })

        return base

    def _resimulate(
        self,
        initial_state: ReservoirState,
        inflow_series: list[float],
        release_series: list[float],
        timestamps: list,
        program_id: str,
    ) -> SimulationResult:
        dt_seconds = 3 * 3600
        n = min(len(inflow_series), len(release_series))
        snapshots: list[StateSnapshot] = []
        state = initial_state

        for i in range(n):
            inflow = inflow_series[i]
            outflow = min(max(release_series[i], 0.0), self.hydraulics.compute_max_discharge(state.level))
            ts = timestamps[i] if i < len(timestamps) else state.timestamp + timedelta(seconds=dt_seconds * i)
            snapshots.append(StateSnapshot(
                timestamp=ts, level=state.level, storage=state.storage,
                inflow=inflow, outflow=outflow, active_module=None,
            ))
            state = self.hydraulics.water_balance_step(state, inflow, outflow, dt_seconds)

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


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------

class InstructionStaticComparator:
    """Aligns Stage 2 extension results against Stage 1 extension oracle."""

    def __init__(self) -> None:
        self._s1: pd.DataFrame | None = None
        self._s2: pd.DataFrame | None = None

    def load_stage1(self, stage1_dir: str | Path) -> "InstructionStaticComparator":
        csv = Path(stage1_dir) / "results.csv"
        self._s1 = pd.read_csv(csv) if csv.exists() else pd.DataFrame()
        return self

    def load_stage2(self, stage2_dir: str | Path) -> "InstructionStaticComparator":
        csv = Path(stage2_dir) / "results.csv"
        self._s2 = pd.read_csv(csv) if csv.exists() else pd.DataFrame()
        return self

    def load_stage2_from_rows(self, rows: list[dict[str, Any]]) -> "InstructionStaticComparator":
        self._s2 = pd.DataFrame(rows) if rows else pd.DataFrame()
        return self

    def compare(self) -> dict[str, Any]:
        if self._s1 is None or self._s2 is None:
            raise RuntimeError("Load both stage1 and stage2 before comparing.")

        s1 = self._s1.copy()
        s2 = self._s2.copy()

        for df in (s1, s2):
            for k in _ALIGN_KEYS:
                if k not in df.columns:
                    df[k] = ""

        def _make_key(df: pd.DataFrame) -> pd.Series:
            if df.empty:
                return pd.Series(dtype=str)
            return df[_ALIGN_KEYS].astype(str).agg("__".join, axis=1)

        s1_key = _make_key(s1)
        s2_key = _make_key(s2)
        s1_set, s2_set = set(s1_key), set(s2_key)
        matched_keys = s1_set & s2_set
        missing_in_s2 = s1_set - s2_set
        extra_in_s2 = s2_set - s1_set

        s1_idx = s1.copy()
        s1_idx["_key"] = s1_key if not s1.empty else pd.Series(dtype=str)
        s2_idx = s2.copy()
        s2_idx["_key"] = s2_key if not s2.empty else pd.Series(dtype=str)

        merged = s1_idx[s1_idx["_key"].isin(matched_keys)].merge(
            s2_idx[s2_idx["_key"].isin(matched_keys)],
            on="_key",
            suffixes=("_s1", "_s2"),
        )

        def _tol_failures(col: str, tol: float) -> int:
            c1 = f"{col}_s1" if f"{col}_s1" in merged.columns else col
            c2 = f"{col}_s2" if f"{col}_s2" in merged.columns else col
            if c1 in merged.columns and c2 in merged.columns:
                return int((abs(merged[c1] - merged[c2]) > tol).sum())
            return 0

        accepted_mismatch = 0
        if "accepted_s1" in merged.columns and "accepted_s2" in merged.columns:
            accepted_mismatch = int((merged["accepted_s1"] != merged["accepted_s2"]).sum())

        max_level_failures = _tol_failures("max_level", _TOL_MAX_LEVEL)
        terminal_dev_failures = _tol_failures("terminal_deviation", _TOL_TERMINAL_DEV)
        peak_reduction_failures = _tol_failures("peak_reduction_rate", _TOL_PEAK_REDUCTION)

        command_compliance_mismatches = 0
        if "command_compliance_s1" in merged.columns and "command_compliance_s2" in merged.columns:
            command_compliance_mismatches = int(
                (merged["command_compliance_s1"] != merged["command_compliance_s2"]).sum()
            )

        interval_compliance_mismatches = 0
        if "interval_compliance_s1" in merged.columns and "interval_compliance_s2" in merged.columns:
            interval_compliance_mismatches = int(
                (merged["interval_compliance_s1"] != merged["interval_compliance_s2"]).sum()
            )

        passes_oracle = (
            accepted_mismatch == 0
            and max_level_failures == 0
            and terminal_dev_failures == 0
            and peak_reduction_failures == 0
            and command_compliance_mismatches == 0
            and interval_compliance_mismatches == 0
            and len(missing_in_s2) == 0
        )

        return {
            "s1_total": len(s1),
            "s2_total": len(s2),
            "matched_rows": len(matched_keys),
            "missing_in_s2": len(missing_in_s2),
            "extra_in_s2": len(extra_in_s2),
            "missing_keys": sorted(missing_in_s2)[:20],
            "extra_keys": sorted(extra_in_s2)[:20],
            "accepted_mismatch": accepted_mismatch,
            "max_level_failures": max_level_failures,
            "terminal_deviation_failures": terminal_dev_failures,
            "peak_reduction_failures": peak_reduction_failures,
            "command_compliance_mismatches": command_compliance_mismatches,
            "interval_compliance_mismatches": interval_compliance_mismatches,
            "passes_oracle": passes_oracle,
        }

    def to_report(self) -> dict[str, Any]:
        return self.compare()
