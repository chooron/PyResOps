"""Rolling dispatch figure: expanded multi-event rolling process."""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from _chapter5_common import (
    C_FORECAST,
    C_INFLOW,
    C_LEVEL,
    C_LIMIT,
    C_RELEASE,
    C_REPLAN,
    C_RETAIN,
    draw_time_step_grid,
    format_time_axis,
    load_rolling_operation_timeseries,
    load_stage1_rolling,
    parse_stage_hour,
    savefig,
    setup_style,
)


ROLLING_EVENTS = [
    (2012062402, "long multi-trigger"),
    (2021052114, "high-volume"),
    (2022062023, "long recession"),
    (2013100711, "extreme inflow"),
    (2024061623, "short high-water"),
]


def _event_rows(results, event_id: int):
    rows = results[results["event_id"].astype(str) == str(event_id)].copy()
    rows["hour"] = rows["workflow_stage"].map(parse_stage_hour)
    rows["idx"] = rows["hour"] / 3.0
    return rows


def _plot_event(row_axes, ro, results, event_id: int) -> None:
    sub = ro[ro["event_id"].astype(str) == str(event_id)].sort_values("time").reset_index(drop=True)
    rows = _event_rows(results, event_id)
    times = sub["time"]

    ax = row_axes[0]
    ax.set_facecolor("none")
    draw_time_step_grid(ax, times)
    ax.plot(times, sub["inflow_observed"], color=C_INFLOW, lw=1.5, label="observed inflow", zorder=-1)
    ax.plot(times, sub["inflow_forecast"], color=C_FORECAST, lw=1.0, ls="--", label="fixed forecast")
    ax.plot(times, sub["release_agent"], color=C_RELEASE, lw=1.15, label="rolling release")
    for _, r in rows.iterrows():
        if r["action"] == "replan":
            idx = min(len(times) - 1, max(0, int(round(float(r["idx"])))))
            ax.axvline(times.iloc[idx], color=C_REPLAN, lw=0.55, alpha=0.35)
    ax.set_ylabel("Flow (m3/s)")
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)

    ax = row_axes[1]
    ax.set_facecolor("none")
    draw_time_step_grid(ax, times)
    ax.plot(times, sub["level_agent"], color=C_LEVEL, lw=1.15, label="level", zorder=-1)
    ax.axhline(sub["flood_limit_level"].iloc[0], color=C_LIMIT, ls="--", lw=0.9, label="flood limit")
    ymin, ymax = float(sub["level_agent"].min()), float(sub["level_agent"].max())
    offset = max((ymax - ymin) * 0.11, 0.06)
    for _, r in rows.iterrows():
        idx = min(len(times) - 1, max(0, int(round(float(r["idx"])))))
        y = ymax + offset if r["action"] == "replan" else ymin - offset
        marker = "o" if r["action"] == "replan" else "s"
        color = C_REPLAN if r["action"] == "replan" else C_RETAIN
        ax.scatter(times.iloc[idx], y, s=19, marker=marker, color=color, alpha=0.95)
    ax.set_ylim(ymin - 2.1 * offset, ymax + 2.1 * offset)
    ax.set_ylabel("Level (m)")
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)


def _add_legend(fig) -> None:
    handles = [
        Line2D([0], [0], color=C_INFLOW, lw=1.5, label="Observed inflow"),
        Line2D([0], [0], color=C_FORECAST, lw=1.1, ls="--", label="Fixed forecast"),
        Line2D([0], [0], color=C_RELEASE, lw=1.2, label="Rolling release"),
        Line2D([0], [0], color=C_LEVEL, lw=1.2, label="Level"),
        Line2D([0], [0], color=C_LIMIT, lw=1.0, ls="--", label="Flood limit"),
        Line2D([0], [0], color=C_REPLAN, marker="o", lw=0, markersize=5, label="Replan"),
        Line2D([0], [0], color=C_RETAIN, marker="s", lw=0, markersize=5, label="Retain"),
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
    ro = load_rolling_operation_timeseries()
    results = load_stage1_rolling()

    fig = plt.figure(figsize=(12.6, 10.4))
    gs = fig.add_gridspec(
        len(ROLLING_EVENTS),
        2,
        hspace=0.34,
        wspace=0.22,
    )

    for row, (event_id, label) in enumerate(ROLLING_EVENTS):
        axes = [fig.add_subplot(gs[row, 0]), fig.add_subplot(gs[row, 1])]
        _plot_event(axes, ro, results, event_id)
    _add_legend(fig)
    fig.subplots_adjust(top=0.92, bottom=0.065)
    savefig(fig, "fig5_3_rolling_dispatch_process", category="dispatch")


if __name__ == "__main__":
    generate()
