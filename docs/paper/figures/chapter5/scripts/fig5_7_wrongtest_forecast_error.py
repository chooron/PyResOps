"""Fig 5-7: Forecast-error wrongtest — 5-event rolling validation under perturbed forecasts.

One row per event (5 rows × 2 columns):
  Left:  inflow (observed) + original forecast + perturbed forecast + rolling release
  Right: trigger type at each replan stage (stacked bar per trigger category)
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
    ROOT,
    format_time_axis,
    savefig,
    setup_style,
)

WRONGTEST_DIR = ROOT / "data" / "wrongtest"
STAGE2_DIR = ROOT / "experiments" / "results" / "paper_validation" / "forecast_error_wrongtest" / "stage2_workflow"
STAGE3_DIR = ROOT / "experiments" / "results" / "paper_validation" / "forecast_error_wrongtest" / "stage3_mimo_mcp"

EVENTS = [
    ("2012062402", "lag_6h",        "2012062402_wrongtest_lag_6h.csv"),
    ("2022062023", "over_peak_mild", "2022062023_wrongtest_over_peak_mild.csv"),
    ("2013100711", "under_peak_mild","2013100711_wrongtest_under_peak_mild.csv"),
    ("2024061623", "lead_6h",        "2024061623_wrongtest_lead_6h.csv"),
    ("2024072617", "mixed_mild",     "2024072617_wrongtest_mixed_mild.csv"),
]

PERTURBATION_LABELS = {
    "lag_6h":        "Lag +6 h",
    "over_peak_mild":"Over-peak +12%",
    "under_peak_mild":"Under-peak −12%",
    "lead_6h":       "Lead −6 h",
    "mixed_mild":    "Mixed mild",
}

TRIGGER_COLORS = {
    "relative_forecast_error":  "#d95f02",
    "absolute_forecast_error":  "#e6ab02",
    "state_risk":               "#b2182b",
    "scheduled_12h_check":      "#7570b3",
}
TRIGGER_LABELS = {
    "relative_forecast_error":  "Relative error",
    "absolute_forecast_error":  "Absolute error",
    "state_risk":               "State risk",
    "scheduled_12h_check":      "Scheduled 12 h",
}
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
            rows.append({
                "event_id": r["event_id"],
                "stage_id": r["stage_id"],
                "replan_reason": r.get("replan_reason", ""),
                "declared_outflow": m.get("declared_outflow"),
                "final_level": m.get("final_level_m"),
            })
    return pd.DataFrame(rows)


def _load_wrongtest_csv(filename: str) -> pd.DataFrame:
    path = WRONGTEST_DIR / filename
    orig_id = filename.split("_wrongtest_")[0]
    orig_path = ROOT / "data" / "withpred" / f"{orig_id}.csv"
    df = pd.read_csv(path, parse_dates=["time"])
    orig = pd.read_csv(orig_path, parse_dates=["time"])
    df = df.merge(orig[["time", "predict"]].rename(columns={"predict": "predict_orig"}), on="time", how="left")
    return df


def _parse_stage_hour(stage_id: str) -> int:
    return int(str(stage_id).replace("rolling_", "").replace("h", ""))


def _plot_event_left(ax, ts: pd.DataFrame, stage_rows: pd.DataFrame) -> None:
    times = ts["time"]
    ax.plot(times, ts["inflow"], color=C_INFLOW, lw=1.4, label="Observed inflow", zorder=3)
    ax.plot(times, ts["predict_orig"], color=C_ORIG_FORECAST, lw=1.0, ls="--", label="Original forecast", zorder=2)
    ax.plot(times, ts["predict"], color=C_FORECAST, lw=1.0, ls=":", label="Perturbed forecast", zorder=2)

    # rolling release: step-wise from declared_outflow at each stage
    if not stage_rows.empty:
        stage_rows = stage_rows.copy()
        stage_rows["hour"] = stage_rows["stage_id"].map(_parse_stage_hour)
        stage_rows = stage_rows.sort_values("hour").reset_index(drop=True)
        release_vals = []
        for i, t in enumerate(times):
            elapsed = int((t - times.iloc[0]).total_seconds() / 3600)
            # find last stage whose hour <= elapsed
            mask = stage_rows["hour"] <= elapsed
            if mask.any():
                val = stage_rows.loc[mask, "declared_outflow"].iloc[-1]
            else:
                val = stage_rows["declared_outflow"].iloc[0]
            release_vals.append(val)
        ax.plot(times, release_vals, color=C_RELEASE, lw=1.2, label="Rolling release", zorder=4)

    ax.set_ylabel("Flow (m³/s)", fontsize=7)
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)
    ax.tick_params(labelsize=7)


def _plot_event_right(ax, stage_rows: pd.DataFrame) -> None:
    if stage_rows.empty:
        ax.axis("off")
        return

    stage_rows = stage_rows.copy()
    stage_rows["hour"] = stage_rows["stage_id"].map(_parse_stage_hour)
    stage_rows = stage_rows.sort_values("hour").reset_index(drop=True)

    trigger_types = list(TRIGGER_COLORS.keys())
    x = np.arange(len(stage_rows))
    bottoms = np.zeros(len(stage_rows))

    for ttype in trigger_types:
        heights = (stage_rows["replan_reason"] == ttype).astype(float).values
        ax.bar(x, heights, bottom=bottoms, color=TRIGGER_COLORS[ttype], width=0.72, alpha=0.88)
        bottoms += heights

    ax.set_xlim(-0.6, len(stage_rows) - 0.4)
    ax.set_ylim(0, 1.35)
    ax.set_yticks([])
    ax.set_xticks(x)
    stage_labels = [str(int(h)) for h in stage_rows["hour"]]
    ax.set_xticklabels(stage_labels, fontsize=6, rotation=45, ha="right")
    ax.set_xlabel("Stage offset (h)", fontsize=7)
    ax.tick_params(axis="x", length=2)


def generate() -> None:
    setup_style()
    stage2 = _load_stage2_jsonl()

    fig = plt.figure(figsize=(12.6, 11.0))
    gs = fig.add_gridspec(len(EVENTS), 2, hspace=0.52, wspace=0.26, width_ratios=[2.8, 1.0])

    for row, (event_id, pert_type, csv_file) in enumerate(EVENTS):
        ts = _load_wrongtest_csv(csv_file)
        eid_full = f"{event_id}_wrongtest_{pert_type}"
        stage_rows = stage2[stage2["event_id"] == eid_full].copy()

        ax_left = fig.add_subplot(gs[row, 0])
        ax_right = fig.add_subplot(gs[row, 1])

        _plot_event_left(ax_left, ts, stage_rows)
        _plot_event_right(ax_right, stage_rows)

        label = PERTURBATION_LABELS[pert_type]
        n_stages = len(stage_rows)
        ax_left.set_title(
            f"({chr(ord('a') + row * 2)}) {event_id}  [{label}]  —  {n_stages} stages",
            fontsize=8, loc="left", pad=3,
        )
        ax_right.set_title(
            f"({chr(ord('a') + row * 2 + 1)}) Trigger types",
            fontsize=8, loc="left", pad=3,
        )

    # legend
    line_handles = [
        Line2D([0], [0], color=C_INFLOW, lw=1.4, label="Observed inflow"),
        Line2D([0], [0], color=C_ORIG_FORECAST, lw=1.0, ls="--", label="Original forecast"),
        Line2D([0], [0], color=C_FORECAST, lw=1.0, ls=":", label="Perturbed forecast"),
        Line2D([0], [0], color=C_RELEASE, lw=1.2, label="Rolling release"),
    ]
    patch_handles = [
        mpatches.Patch(color=TRIGGER_COLORS[t], alpha=0.88, label=TRIGGER_LABELS[t])
        for t in TRIGGER_COLORS
    ]
    fig.legend(
        handles=line_handles + patch_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=8,
        frameon=False,
        fontsize=8,
        handlelength=2.0,
        columnspacing=0.9,
    )

    fig.suptitle(
        "Fig. 5-7  Forecast-error wrongtest: rolling operation under perturbed forecasts (5 events)",
        y=1.002, fontsize=9, weight="bold",
    )
    fig.subplots_adjust(top=0.935, bottom=0.055)
    savefig(fig, "fig5_7_wrongtest_forecast_error", category="dispatch")


if __name__ == "__main__":
    generate()
