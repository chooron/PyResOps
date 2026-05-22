"""Dynamic dispatch figure: multiple command calls across multiple flood events."""

from __future__ import annotations

from dataclasses import replace

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

from _chapter5_common import (
    COMMAND_LABELS,
    C_INFLOW,
    C_LEVEL,
    C_LIMIT,
    DISPATCH_DATA_OUT,
    FAMILY_COLORS,
    FAMILY_STYLES,
    draw_time_step_grid,
    format_time_axis,
    load_processed_event,
    savefig,
    setup_style,
)
from experiments.data_adapters.real_events import FloodEventData
from experiments.stage1.checkpoints import compute_dynamic_checkpoints
from experiments.stage1.constraints import (
    build_tankan_constraints,
    build_tankan_task_constraints,
    get_flood_limit,
    get_season_name,
)
from experiments.stage1.dynamic_command_intervention import (
    CheckpointState,
    DynamicCommandInterventionRunner,
    build_command,
    replan_with_command,
)


EVENT_SEQUENCES: dict[int, list[tuple[str, str]]] = {
    2010062002: [
        ("C1", "D1_release_cap_adjustment"),
        ("C2", "D2_terminal_target_lowering"),
        ("C3", "D4_conservative_risk_buffer"),
    ],
    2024061517: [
        ("C1", "D4_conservative_risk_buffer"),
        ("C2", "D1_release_cap_adjustment"),
        ("C3", "D2_terminal_target_lowering"),
    ],
    2024061623: [
        ("C1", "D1_release_cap_adjustment"),
        ("C2", "D4_conservative_risk_buffer"),
        ("C3", "D2_terminal_target_lowering"),
    ],
}

CHECKPOINT_LABELS = {
    "C1": "C1",
    "C2": "C2",
    "C3": "C3",
}
COMMAND_COLORS = {
    "D1_release_cap_adjustment": FAMILY_COLORS[0],
    "D2_terminal_target_lowering": FAMILY_COLORS[1],
    "D3_target_deadline_compression": FAMILY_COLORS[2],
    "D4_conservative_risk_buffer": FAMILY_COLORS[3],
}
COMMAND_STYLES = {
    "D1_release_cap_adjustment": FAMILY_STYLES[0],
    "D2_terminal_target_lowering": FAMILY_STYLES[1],
    "D3_target_deadline_compression": FAMILY_STYLES[2],
    "D4_conservative_risk_buffer": FAMILY_STYLES[3],
}
COMMAND_CODES = {
    "D1_release_cap_adjustment": "D1",
    "D2_terminal_target_lowering": "D2",
    "D3_target_deadline_compression": "D3",
    "D4_conservative_risk_buffer": "D4",
}

_RUNNER: DynamicCommandInterventionRunner | None = None
_STATE_CACHE: dict[tuple[int, str], CheckpointState] = {}
_TRACE_CACHE: dict[tuple[int, str, str, float], pd.DataFrame] = {}


def _runner() -> DynamicCommandInterventionRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = DynamicCommandInterventionRunner(data_root="data")
    return _RUNNER


def _build_sequence_states(event: FloodEventData) -> dict[str, CheckpointState]:
    """Build dynamic command checkpoints using the Stage 1 adaptive time rule."""
    runner = _runner()
    spec = runner.spec
    inflows = [r.inflow for r in event.records if r.inflow is not None]
    cp_indices = compute_dynamic_checkpoints(inflows, event.time_step_hours)
    if len(cp_indices) < 4:
        raise ValueError(f"{event.event_id}: too few dynamic checkpoints for sequence display")

    sequence_indices = sorted(cp_indices[1:4])
    label_to_index = {f"C{i + 1}": cp_idx for i, cp_idx in enumerate(sequence_indices)}
    first_event_rec = event.records[0]
    flood_limit = get_flood_limit(first_event_rec.time.month, first_event_rec.time.day)
    season = get_season_name(first_event_rec.time.month, first_event_rec.time.day)
    constraints = build_tankan_constraints(first_event_rec.time.month, first_event_rec.time.day)
    task_constraints = build_tankan_task_constraints(flood_limit)

    states: dict[str, CheckpointState] = {}
    for label, cp_idx in label_to_index.items():
        offset_hours = cp_idx * event.time_step_hours
        sliced = event.slice_from_hour(offset_hours)
        first_idx = sliced.first_valid_index()
        first_rec = sliced.records[first_idx]
        initial_level = first_rec.level if first_rec.level is not None else spec.initial_level
        sliced_inflows = [r.inflow for r in sliced.records if r.inflow is not None]
        states[label] = CheckpointState(
            event_id=event.event_id,
            checkpoint_id=label,
            checkpoint_hour=offset_hours,
            checkpoint_idx=cp_idx,
            sliced_event=sliced,
            initial_level=float(initial_level),
            flood_limit=flood_limit,
            season=season,
            peak_inflow=max(sliced_inflows) if sliced_inflows else 0.0,
            constraints=dict(constraints),
            task_constraints=dict(task_constraints),
        )
    return states


def _checkpoint_state(event_id: int, checkpoint_id: str) -> CheckpointState:
    key = (event_id, checkpoint_id)
    if key not in _STATE_CACHE:
        event = _runner().adapter.load_event(str(event_id))
        _STATE_CACHE.update({(event_id, k): v for k, v in _build_sequence_states(event).items()})
    return _STATE_CACHE[key]


def _dynamic_trace(
    event_id: int,
    checkpoint_id: str,
    command_type: str,
    initial_level: float,
) -> pd.DataFrame:
    key = (event_id, checkpoint_id, command_type, round(float(initial_level), 4))
    if key in _TRACE_CACHE:
        return _TRACE_CACHE[key]

    runner = _runner()
    observed_cp_state = _checkpoint_state(event_id, checkpoint_id)
    cp_state = replace(observed_cp_state, initial_level=float(initial_level))
    command = build_command(command_type, cp_state)
    success, opt_result, reason = replan_with_command(
        cp_state,
        command,
        runner.optimization_service,
        runner.routing_check,
        runner.spec,
    )
    if not success or opt_result is None or not opt_result.selected_candidate.feasible:
        raise RuntimeError(
            f"Dynamic command simulation failed: event={event_id}, checkpoint={checkpoint_id}, "
            f"command={command_type}, reason={reason or 'infeasible_candidate'}"
        )

    trace = pd.DataFrame(
        [
            {
                "time": snap.timestamp,
                "release": snap.outflow,
                "level": snap.level,
                "inflow": snap.inflow,
                "flood_limit": cp_state.flood_limit,
                "checkpoint_hour": cp_state.checkpoint_hour,
                "checkpoint_time": snap.timestamp if i == 0 else pd.NaT,
                "initial_level_used": cp_state.initial_level,
                "observed_checkpoint_level": observed_cp_state.initial_level,
            }
            for i, snap in enumerate(opt_result.selected_candidate.simulation_result.snapshots)
        ]
    )
    trace["checkpoint_time"] = trace["checkpoint_time"].ffill()
    _TRACE_CACHE[key] = trace
    return trace


def _segment_trace(
    event_id: int,
    checkpoint_id: str,
    command_type: str,
    initial_level: float,
    next_time: pd.Timestamp | None,
) -> pd.DataFrame:
    trace = _dynamic_trace(event_id, checkpoint_id, command_type, initial_level).copy()
    if next_time is not None:
        trace = trace[trace["time"] <= next_time].copy()
    return trace


def _plot_event_row(axes, event_id: int, sequence: list[tuple[str, str]]) -> list[pd.DataFrame]:
    event = load_processed_event(event_id)
    checkpoints = [_checkpoint_state(event_id, checkpoint_id) for checkpoint_id, _ in sequence]
    call_times = [
        pd.Timestamp(cp.sliced_event.records[cp.sliced_event.first_valid_index()].time)
        for cp in checkpoints
    ]
    flood_limit = checkpoints[0].flood_limit

    ax_flow, ax_level = axes
    ax_flow.set_facecolor("none")
    ax_level.set_facecolor("none")
    draw_time_step_grid(ax_flow, event["time"])
    draw_time_step_grid(ax_level, event["time"])
    ax_flow.plot(event["time"], event["inflow_observed"], color=C_INFLOW, lw=1.5, zorder=-1)
    ax_level.plot(event["time"], event["level_state"], color=C_LEVEL, lw=1.2, zorder=-1)
    ax_level.axhline(flood_limit, color=C_LIMIT, ls="--", lw=0.9)

    export_rows: list[pd.DataFrame] = []
    execution_level = float(checkpoints[0].initial_level)
    for i, ((checkpoint_id, command_type), call_time) in enumerate(zip(sequence, call_times)):
        next_time = call_times[i + 1] if i + 1 < len(call_times) else None
        initial_level = execution_level
        segment = _segment_trace(event_id, checkpoint_id, command_type, initial_level, next_time)
        if segment.empty:
            raise RuntimeError(f"No segment snapshots for event={event_id}, checkpoint={checkpoint_id}")
        execution_level = float(segment["level"].iloc[-1])
        color = COMMAND_COLORS[command_type]
        style = COMMAND_STYLES[command_type]

        ax_flow.step(segment["time"], segment["release"], where="post", color=color, ls=style, lw=1.35)
        ax_level.plot(segment["time"], segment["level"], color=color, ls=style, lw=1.35)

        for ax in (ax_flow, ax_level):
            ax.axvline(call_time, color="#555555", lw=0.75, alpha=0.65)
        ymin, ymax = ax_flow.get_ylim()
        label_y = ymin + (ymax - ymin) * (0.93 - 0.08 * (i % 3))
        ax_flow.text(
            call_time,
            label_y,
            f"{CHECKPOINT_LABELS[checkpoint_id]}-{COMMAND_CODES[command_type]}",
            ha="center",
            va="top",
            fontsize=11.0,
            color=color,
            bbox={"facecolor": "white", "alpha": 0.72, "edgecolor": "none", "pad": 1.2},
        )

        out = segment.copy()
        out.insert(0, "segment_end_time", next_time)
        out.insert(0, "command_type", command_type)
        out.insert(0, "checkpoint_id", checkpoint_id)
        out.insert(0, "command_order", i + 1)
        out.insert(0, "chain_initial_level", initial_level)
        out.insert(0, "chain_terminal_level", execution_level)
        out.insert(0, "event_id", event_id)
        export_rows.append(out)

    ax_flow.set_ylabel(r"Flow (m$^3$/s)")
    ax_level.set_ylabel("Level (m)")
    for ax in axes:
        ax.set_xlim(event["time"].iloc[0], event["time"].iloc[-1])
        format_time_axis(ax)
    return export_rows


def _add_legend(fig) -> None:
    handles = [
        Line2D([0], [0], color=C_INFLOW, lw=1.5, label="Observed inflow"),
        Line2D([0], [0], color=C_LEVEL, lw=1.2, label="Observed level"),
    ]
    used_commands = []
    for sequence in EVENT_SEQUENCES.values():
        for _, command in sequence:
            if command not in used_commands:
                used_commands.append(command)
    for command in used_commands:
        handles.append(
            Line2D(
                [0],
                [0],
                color=COMMAND_COLORS[command],
                ls=COMMAND_STYLES[command],
                lw=1.4,
                label=f"{COMMAND_CODES[command]} {COMMAND_LABELS[command]}",
            )
        )
    handles.append(Line2D([0], [0], color=C_LIMIT, lw=0.9, ls="--", label="Flood limit"))
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.92),
        ncol=6,
        frameon=False,
        fontsize=11,
        handlelength=2.1,
        columnspacing=1.0,
    )


def generate() -> None:
    setup_style()
    fig = plt.figure(figsize=(12.4, 7.8))
    gs = fig.add_gridspec(len(EVENT_SEQUENCES), 2, hspace=0.36, wspace=0.22)

    trace_rows: list[pd.DataFrame] = []
    for row, (event_id, sequence) in enumerate(EVENT_SEQUENCES.items()):
        axes = [fig.add_subplot(gs[row, 0]), fig.add_subplot(gs[row, 1])]
        trace_rows.extend(_plot_event_row(axes, event_id, sequence))
    _add_legend(fig)
    fig.subplots_adjust(top=0.93, bottom=0.075)
    savefig(fig, "fig5_2_dynamic_command_dispatch", category="dispatch")

    pd.concat(trace_rows, ignore_index=True).to_csv(
        DISPATCH_DATA_OUT / "fig5_2_dynamic_command_dispatch_trace.csv",
        index=False,
        encoding="utf-8",
    )


if __name__ == "__main__":
    generate()
