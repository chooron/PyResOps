"""Unified metric extraction for Stage 1 baseline results."""

from __future__ import annotations

import statistics
from typing import Any

from pyresops.domain.result import SimulationResult
from pyresops.services.optimization import ReleaseOptimizationResult


def extract_unified_metrics(
    event_id: str,
    scenario_type: str,
    scenario_group: str,
    opt_result: ReleaseOptimizationResult,
    sim_result: SimulationResult,
    routing_max_flow: float,
    downstream_violation: bool,
    flood_limit: float,
    season: str,
    workflow_stage: str = "static",
    trigger_type: str | None = None,
    action: str | None = None,
    initial_level: float | None = None,
) -> dict[str, Any]:
    """Return the unified metrics record for one optimization result."""
    snapshots = sim_result.snapshots
    candidate = opt_result.selected_candidate

    levels = [s.level for s in snapshots]
    outflows = [s.outflow for s in snapshots]
    inflows = [s.inflow for s in snapshots]

    terminal_level = levels[-1] if levels else float("nan")
    terminal_deviation = abs(terminal_level - flood_limit) if levels else float("nan")

    peak_inflow = max(inflows) if inflows else float("nan")
    peak_release = max(outflows) if outflows else float("nan")
    max_level = max(levels) if levels else float("nan")

    peak_reduction_rate = (
        (peak_inflow - peak_release) / peak_inflow
        if peak_inflow and peak_inflow > 0
        else float("nan")
    )

    # Release smoothness: std of step-to-step changes
    release_deltas = [abs(outflows[i] - outflows[i - 1]) for i in range(1, len(outflows))]
    release_smoothness = statistics.stdev(release_deltas) if len(release_deltas) >= 2 else 0.0

    # Volumes (m3/s × 3h → 亿m3)
    dt_seconds = 3 * 3600
    total_inflow_volume = sum(inflows) * dt_seconds / 1e8
    total_release_volume = sum(outflows) * dt_seconds / 1e8

    hard_violation = not candidate.feasible
    violation_details = "; ".join(
        v.get("violation_type", str(v)) for v in candidate.violations
    ) if candidate.violations else ""

    return {
        "event_id": event_id,
        "scenario_type": scenario_type,
        "scenario_group": scenario_group,
        "workflow_stage": workflow_stage,
        "accepted": candidate.feasible,
        "hard_violation": hard_violation,
        "violation_details": violation_details,
        "initial_level": initial_level if initial_level is not None else (levels[0] if levels else float("nan")),
        "max_level": round(max_level, 3),
        "terminal_level": round(terminal_level, 3),
        "terminal_deviation": round(terminal_deviation, 3),
        "peak_inflow": round(peak_inflow, 1),
        "peak_release": round(peak_release, 1),
        "peak_reduction_rate": round(peak_reduction_rate, 4) if peak_reduction_rate == peak_reduction_rate else float("nan"),
        "max_release": round(peak_release, 1),
        "release_smoothness": round(release_smoothness, 2),
        "total_inflow_volume_1e8m3": round(total_inflow_volume, 4),
        "total_release_volume_1e8m3": round(total_release_volume, 4),
        "routing_max_flow_hecheng": round(routing_max_flow, 1),
        "downstream_violation": downstream_violation,
        "trigger_type": trigger_type or "",
        "action": action or "",
        "optimization_family": candidate.module_type,
        "optimization_score": round(candidate.objective_score, 6),
        "flood_limit_applied": flood_limit,
        "season": season,
    }
