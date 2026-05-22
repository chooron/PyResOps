"""Wrongtest figure: rolling operation under perturbed forecasts (5 events).

Layout mirrors fig5_3_rolling_dispatch_process: 5 rows × 2 columns.
  Left:  observed inflow + original forecast + perturbed forecast + rolling release
  Right: reservoir level + flood limit + replan/retain markers
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from _chapter5_common import (
    C_FORECAST,
    C_INFLOW,
    C_LEVEL,
    C_LIMIT,
    C_RELEASE,
    C_REPLAN,
    C_RETAIN,
    ROOT,
    draw_time_step_grid,
    format_time_axis,
    savefig,
    setup_style,
)

WRONGTEST_DIR = ROOT / "data" / "wrongtest"
STAGE2_DIR = (
    ROOT
    / "experiments"
    / "results"
    / "paper_validation"
    / "forecast_error_wrongtest"
    / "stage2_workflow"
)

EVENTS = [
    ("2012062402", "lag_6h",         "2012062402_wrongtest_lag_6h.csv"),
    ("2022062023", "over_peak_mild",  "2022062023_wrongtest_over_peak_mild.csv"),
    ("2013100711", "under_peak_mild", "2013100711_wrongtest_under_peak_mild.csv"),
    ("2024061623", "lead_6h",         "2024061623_wrongtest_lead_6h.csv"),
    ("2024072617", "mixed_mild",      "2024072617_wrongtest_mixed_mild.csv"),
]

PERTURBATION_LABELS = {
    "lag_6h":         "lag +6 h",
    "over_peak_mild": "over-peak +12%",
    "under_peak_mild":"under-peak −12%",
    "lead_6h":        "lead −6 h",
    "mixed_mild":     "mixed mild",
}

# original forecast line colour (distinct from perturbed)
C_ORIG_FORECAST = "#4575b4"


def _load_stage2_jsonl() -> pd.DataFrame:
    paths = sorted(STAGE2_DIR.glob("stage2_wrongtest_*.jsonl"))
    if not paths:
        raise FileNotFoundError(f"No stage2 JSONL in {STAGE2_DIR}")
    rows = []
    with open(paths[-1], encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            m = r.get("metrics") or {}
            rows.append(
                {
                    "event_id": r["event_id"],
                    "stage_id": r["stage_id"],
                    "replan_reason": r.get("replan_reason", ""),
                    "action": "replan",
                    "declared_outflow": m.get("declared_outflow"),
                    "final_level": m.get("final_level_m"),
                }
            )
    return pd.DataFrame(rows)


def _parse_stage_hour(stage_id: str) -> int:
    return int(str(stage_id).replace("rolling_", "").replace("h", ""))


def _load_wrongtest_csv(filename: str) -> pd.DataFrame:
    path = WRONGTEST_DIR / filename
    orig_id = filename.split("_wrongtest_")[0]
    orig_path = ROOT / "data" / "withpred" / f"{orig_id}.csv"
    df = pd.read_csv(path, parse_dates=["time"])
    orig = pd.read_csv(orig_path, parse_dates=["time"])
    df = df.merge(
        orig[["time", "predict"]].rename(columns={"predict": "predict_orig"}),
        on="time",
        how="left",
    )
    return df


def _build_release_series(times: pd.Series, stage_rows: pd.DataFrame) -> list[float]:
    """Step-wise release from declared_outflow at each stage offset."""
    stage_rows = stage_rows.copy()
    stage_rows["hour"] = stage_rows["stage_id"].map(_parse_stage_hour)
    stage_rows = stage_rows.sort_values("hour").reset_index(drop=True)
    release_vals = []
    for t in times:
        elapsed = int((t - times.iloc[0]).total_seconds() / 3600)
        mask = stage_rows["hour"] <= elapsed
        val = (
            stage_rows.loc[mask, "declared_outflow"].iloc[-1]
            if mask.any()
            else stage_rows["declared_outflow"].iloc[0]
        )
        release_vals.append(val)
    return release_vals


def _plot_event(row_axes, ts: pd.DataFrame, stage_rows: pd.DataFrame) -> None:
    times = ts["time"]

    # ── left: flow ──────────────────────────────────────────────────────────
    ax = row_axes[0]
    ax.set_facecolor("none")
    draw_time_step_grid(ax, times)
    ax.plot(times, ts["inflow"], color=C_INFLOW, lw=1.5, label="Observed inflow", zorder=3)
    ax.plot(
        times, ts["predict_orig"],
        color=C_ORIG_FORECAST, lw=1.0, ls="--", label="Original forecast", zorder=2,
    )
    ax.plot(
        times, ts["predict"],
        color=C_FORECAST, lw=1.0, ls=":", label="Perturbed forecast", zorder=2,
    )
    if not stage_rows.empty:
        release_vals = _build_release_series(times, stage_rows)
        ax.plot(times, release_vals, color=C_RELEASE, lw=1.15, label="Rolling release", zorder=4)
        # replan verticals
        sr = stage_rows.copy()
        sr["hour"] = sr["stage_id"].map(_parse_stage_hour)
        for _, r in sr.iterrows():
            elapsed = int(r["hour"])
            idx = min(len(times) - 1, max(0, elapsed * 2 // 3))  # approx index
            # find closest time index
            target = times.iloc[0] + pd.Timedelta(hours=elapsed)
            idx = int((times - target).abs().argmin())
            ax.axvline(times.iloc[idx], color=C_REPLAN, lw=0.55, alpha=0.35)
    ax.set_ylabel(r"Flow (m$^3$/s)")
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)

    # ── right: level ─────────────────────────────────────────────────────────
    ax = row_axes[1]
    ax.set_facecolor("none")
    draw_time_step_grid(ax, times)
    ax.plot(times, ts["level"], color=C_LEVEL, lw=1.15, label="Level", zorder=2)

    # flood limit from manifest (use a fixed value per event if available)
    # fall back to a horizontal line at max level + 0.5 if not present
    if "flood_limit" in ts.columns:
        flood_limit = float(ts["flood_limit"].iloc[0])
    else:
        flood_limit = float(ts["level"].max()) + 0.5
    ax.axhline(flood_limit, color=C_LIMIT, ls="--", lw=0.9, label="Flood limit")

    ymin = float(ts["level"].min())
    ymax = float(ts["level"].max())
    offset = max((ymax - ymin) * 0.11, 0.06)

    if not stage_rows.empty:
        sr = stage_rows.copy()
        sr["hour"] = sr["stage_id"].map(_parse_stage_hour)
        for _, r in sr.iterrows():
            target = times.iloc[0] + pd.Timedelta(hours=int(r["hour"]))
            idx = int((times - target).abs().argmin())
            y = ymax + offset
            ax.scatter(
                times.iloc[idx], y,
                s=19, marker="o", color=C_REPLAN, alpha=0.95,
            )
    ax.set_ylim(ymin - 2.1 * offset, ymax + 2.1 * offset)
    ax.set_ylabel("Level (m)")
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)


def _add_legend(fig) -> None:
    handles = [
        Line2D([0], [0], color=C_INFLOW, lw=1.5, label="Observed inflow"),
        Line2D([0], [0], color=C_ORIG_FORECAST, lw=1.0, ls="--", label="Original forecast"),
        Line2D([0], [0], color=C_FORECAST, lw=1.0, ls=":", label="Perturbed forecast"),
        Line2D([0], [0], color=C_RELEASE, lw=1.2, label="Rolling release"),
        Line2D([0], [0], color=C_LEVEL, lw=1.2, label="Level"),
        Line2D([0], [0], color=C_LIMIT, lw=1.0, ls="--", label="Flood limit"),
        Line2D([0], [0], color=C_REPLAN, marker="o", lw=0, markersize=5, label="Replan"),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.99),
        ncol=7,
        frameon=False,
        handlelength=2.2,
        columnspacing=1.0,
    )


def generate() -> None:
    setup_style()
    stage2 = _load_stage2_jsonl()

    fig = plt.figure(figsize=(12.6, 10.4))
    gs = fig.add_gridspec(len(EVENTS), 2, hspace=0.34, wspace=0.22)

    for row, (event_id, pert_type, csv_file) in enumerate(EVENTS):
        ts = _load_wrongtest_csv(csv_file)
        eid_full = f"{event_id}_wrongtest_{pert_type}"
        stage_rows = stage2[stage2["event_id"] == eid_full].copy()

        axes = [fig.add_subplot(gs[row, 0]), fig.add_subplot(gs[row, 1])]
        _plot_event(axes, ts, stage_rows)

        label = PERTURBATION_LABELS[pert_type]
        n = len(stage_rows)
        axes[0].set_title(
            f"({chr(ord('a') + row * 2)}) {event_id}  [{label}]  —  {n} stages",
            fontsize=10, loc="left", pad=3,
        )
        axes[1].set_title(
            f"({chr(ord('a') + row * 2 + 1)}) Reservoir level",
            fontsize=10, loc="left", pad=3,
        )

    _add_legend(fig)
    fig.subplots_adjust(top=0.92, bottom=0.065)
    savefig(fig, "fig5_4_wrongtest_forecast_error", category="dispatch")


if __name__ == "__main__":
    generate()
