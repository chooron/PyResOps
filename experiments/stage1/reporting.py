"""Summary reporting for Stage 1 baseline results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def generate_summary_tables(
    static_metrics: list[dict[str, Any]],
    dynamic_metrics: list[dict[str, Any]],
    rolling_metrics: list[dict[str, Any]],
    output_dir: str | Path,
) -> None:
    """Write per-workflow CSVs and an aggregated summary table."""
    out = Path(output_dir)

    if static_metrics:
        static_dir = out / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        df_static = pd.DataFrame(static_metrics)
        df_static.to_csv(static_dir / "all_events_metrics.csv", index=False)
        _write_trajectories(static_metrics, static_dir / "trajectories")

    if dynamic_metrics:
        dyn_dir = out / "dynamic"
        dyn_dir.mkdir(parents=True, exist_ok=True)
        df_dyn = pd.DataFrame(dynamic_metrics)
        df_dyn.to_csv(dyn_dir / "stage_results.csv", index=False)
        retain_cols = ["event_id", "workflow_stage", "action", "trigger_type", "terminal_deviation"]
        df_dyn[[c for c in retain_cols if c in df_dyn.columns]].to_csv(
            dyn_dir / "retain_replan_log.csv", index=False
        )

    if rolling_metrics:
        roll_dir = out / "rolling"
        roll_dir.mkdir(parents=True, exist_ok=True)
        df_roll = pd.DataFrame(rolling_metrics)
        df_roll.to_csv(roll_dir / "stage_results.csv", index=False)
        trigger_cols = ["event_id", "workflow_stage", "trigger_type", "action", "max_level", "terminal_deviation"]
        df_roll[[c for c in trigger_cols if c in df_roll.columns]].to_csv(
            roll_dir / "trigger_log.csv", index=False
        )

    all_metrics = static_metrics + dynamic_metrics + rolling_metrics
    if not all_metrics:
        return

    summary_dir = out / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    df_all = pd.DataFrame(all_metrics)

    # Aggregate by scenario_group
    group_cols = ["scenario_group"]
    agg_cols = {
        "event_id": "count",
        "accepted": "sum",
        "hard_violation": "sum",
        "max_level": "mean",
        "terminal_deviation": "mean",
        "peak_reduction_rate": "mean",
        "release_smoothness": "mean",
        "downstream_violation": "sum",
    }
    available = {k: v for k, v in agg_cols.items() if k in df_all.columns}
    df_summary = df_all.groupby(group_cols).agg(available).reset_index()
    df_summary.to_csv(summary_dir / "stage1_summary_table.csv", index=False)

    # Overall stats JSON
    stats: dict[str, Any] = {
        "total_runs": len(all_metrics),
        "static_runs": len(static_metrics),
        "dynamic_runs": len(dynamic_metrics),
        "rolling_runs": len(rolling_metrics),
        "accepted_count": int(df_all["accepted"].sum()) if "accepted" in df_all.columns else None,
        "hard_violation_count": int(df_all["hard_violation"].sum()) if "hard_violation" in df_all.columns else None,
        "downstream_violation_count": int(df_all["downstream_violation"].sum()) if "downstream_violation" in df_all.columns else None,
        "mean_terminal_deviation": round(float(df_all["terminal_deviation"].mean()), 3) if "terminal_deviation" in df_all.columns else None,
        "mean_peak_reduction_rate": round(float(df_all["peak_reduction_rate"].mean()), 4) if "peak_reduction_rate" in df_all.columns else None,
    }
    (summary_dir / "stage1_metrics.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_trajectories(metrics: list[dict[str, Any]], traj_dir: Path) -> None:
    """Write per-event trajectory JSON stubs (level/release/inflow arrays not yet stored in metrics)."""
    traj_dir.mkdir(parents=True, exist_ok=True)
    for row in metrics:
        event_id = row.get("event_id", "unknown")
        stub = {
            "event_id": event_id,
            "max_level": row.get("max_level"),
            "terminal_level": row.get("terminal_level"),
            "peak_inflow": row.get("peak_inflow"),
            "peak_release": row.get("peak_release"),
        }
        (traj_dir / f"{event_id}.json").write_text(
            json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8"
        )
