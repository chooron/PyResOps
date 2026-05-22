"""Static dispatch figure: instruction-conditioned release schemes.

The figure shows how six operator-specified release families execute on
multiple flood events. Statistical compliance results are intentionally kept in
the separate success-rate figure.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

from _chapter5_common import (
    C_INFLOW,
    C_LIMIT,
    DISPATCH_DATA_OUT,
    FAMILY_COLORS,
    FAMILY_LABELS,
    FAMILY_ORDER,
    FAMILY_STYLES,
    format_time_axis,
    savefig,
    setup_style,
)
from experiments.stage1.constraints import build_tankan_constraints, get_flood_limit
from experiments.stage1.instruction_static import InstructionStaticRunner, quantize_to_interval
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.reservoir import ReservoirState


STATIC_EVENTS = [
    (2024061623, "high water"),
    (2010062002, "release active"),
    (2012062402, "long horizon"),
]

_RUNNER: InstructionStaticRunner | None = None
_TRACE_CACHE: dict[tuple[int, str, int], pd.DataFrame] = {}


def _runner() -> InstructionStaticRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = InstructionStaticRunner(data_root="data")
    return _RUNNER


def _static_trace(event_id: int, family: str, interval_h: int) -> pd.DataFrame:
    key = (event_id, family, interval_h)
    if key in _TRACE_CACHE:
        return _TRACE_CACHE[key]

    runner = _runner()
    event = runner.adapter.load_event(str(event_id))
    first_idx = event.first_valid_index()
    first = event.records[first_idx]
    usable = event.records[first_idx:]

    initial_state = ReservoirState(
        timestamp=first.time,
        level=float(first.level),
        storage=float(runner.spec.level_storage_curve.get_storage(float(first.level))),
        inflow=float(first.inflow),
        outflow=float(first.outflow) if first.outflow is not None else float(first.inflow),
    )
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

    constraints = build_tankan_constraints(first.time.month, first.time.day)
    flood_limit = get_flood_limit(first.time.month, first.time.day)
    opt_result = runner.optimization_service.optimize_release_plan(
        initial_state=initial_state,
        forecast=forecast,
        constraints=constraints,
        task_constraints={"target_level": flood_limit, "target_tolerance": 0.5},
        requested_module_type=family,
        name=f"fig_static_{event_id}_{family}_{interval_h}h",
    )
    raw_release = [s.outflow for s in opt_result.selected_candidate.simulation_result.snapshots]
    k = max(1, int(interval_h // event.time_step_hours))
    release = quantize_to_interval(raw_release, k)
    sim = runner._resimulate(
        initial_state=initial_state,
        inflow_series=forecast_values,
        release_series=release,
        timestamps=timestamps,
        program_id=opt_result.program.id,
    )
    rows = [
        {
            "time": snap.timestamp,
            "inflow": snap.inflow,
            "release": snap.outflow,
            "level": snap.level,
            "flood_limit": flood_limit,
        }
        for snap in sim.snapshots
    ]
    trace = pd.DataFrame(rows)
    _TRACE_CACHE[key] = trace
    return trace


def _draw_interval_grid(ax, times: pd.Series, interval_h: int) -> None:
    if len(times) == 0:
        return
    start = times.iloc[0]
    end = times.iloc[-1]
    tick = start + pd.Timedelta(hours=interval_h)
    while tick <= end:
        ax.axvline(tick, color="#c7c7c7", lw=0.45, alpha=0.55, zorder=-2)
        tick += pd.Timedelta(hours=interval_h)


def _plot_event_row(axes, event_id: int, interval_h: int) -> None:
    traces = {family: _static_trace(event_id, family, interval_h) for family in FAMILY_ORDER}
    first_trace = traces[FAMILY_ORDER[0]]
    times = first_trace["time"]

    ax = axes[0]
    ax.set_facecolor("none")
    ax.plot(times, first_trace["inflow"], color=C_INFLOW, lw=1.5, label="Inflow", zorder=-1)
    _draw_interval_grid(ax, times, interval_h)
    for i, family in enumerate(FAMILY_ORDER):
        trace = traces[family]
        ax.step(
            trace["time"],
            trace["release"],
            where="post",
            color=FAMILY_COLORS[i],
            linestyle=FAMILY_STYLES[i],
            lw=1.1,
            label=FAMILY_LABELS[family],
        )
    ax.set_ylabel(r"Flow (m$^3$/s)")
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)

    ax = axes[1]
    ax.set_facecolor("none")
    _draw_interval_grid(ax, times, interval_h)
    limits = []
    for i, family in enumerate(FAMILY_ORDER):
        trace = traces[family]
        ax.plot(
            trace["time"],
            trace["level"],
            color=FAMILY_COLORS[i],
            linestyle=FAMILY_STYLES[i],
            lw=1.1,
            label=FAMILY_LABELS[family],
        )
        limits.extend(trace["level"].tolist())
    flood_limit = float(first_trace["flood_limit"].iloc[0])
    ax.axhline(flood_limit, color=C_LIMIT, ls="--", lw=1.0, label="Flood limit")
    ax.set_ylabel("Level (m)")
    ax.set_xlim(times.iloc[0], times.iloc[-1])
    format_time_axis(ax)
    if limits:
        pad = max(0.35, (max(limits) - min(limits)) * 0.18)
        ax.set_ylim(min(limits) - pad, max(max(limits), flood_limit) + pad)


def _add_legend(fig) -> None:
    handles = [Line2D([0], [0], color=C_INFLOW, lw=1.5, label="Inflow")]
    for i, family in enumerate(FAMILY_ORDER):
        handles.append(
            Line2D(
                [0],
                [0],
                color=FAMILY_COLORS[i],
                linestyle=FAMILY_STYLES[i],
                lw=1.25,
                label=FAMILY_LABELS[family],
            )
        )
    handles.append(Line2D([0], [0], color=C_LIMIT, ls="--", lw=1.0, label="Flood limit"))
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.95),
        ncol=4,
        frameon=False,
        handlelength=2.4,
        columnspacing=1.1,
    )


def generate(interval_h: int = 6) -> None:
    setup_style()
    fig = plt.figure(figsize=(12.2, 7.8))
    gs = fig.add_gridspec(3, 2, hspace=0.36, wspace=0.22)
    trace_rows: list[pd.DataFrame] = []

    for row, (event_id, label) in enumerate(STATIC_EVENTS):
        axes = [fig.add_subplot(gs[row, 0]), fig.add_subplot(gs[row, 1])]
        _plot_event_row(axes, event_id, interval_h)
        for family in FAMILY_ORDER:
            trace = _static_trace(event_id, family, interval_h).copy()
            trace.insert(0, "operation_interval_h", interval_h)
            trace.insert(0, "release_family", family)
            trace.insert(0, "event_id", event_id)
            trace_rows.append(trace)
    _add_legend(fig)
    fig.subplots_adjust(bottom=0.075, top=0.93)
    savefig(fig, "fig5_1_static_instruction_dispatch", category="dispatch")
    pd.concat(trace_rows, ignore_index=True).to_csv(
        DISPATCH_DATA_OUT / "fig5_1_static_instruction_dispatch_trace.csv",
        index=False,
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
