"""Shared helpers for Chapter 5 paper figures.

The figure scripts in this directory are read-only with respect to experiment
results. They assemble publication-facing assets from frozen CSV/JSON outputs.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[5]
RESULTS = ROOT / "experiments" / "results"
CHAPTER5_DIR = ROOT / "docs" / "paper" / "figures" / "chapter5"
GENERATED = CHAPTER5_DIR / "generated"
DISPATCH_OUT = GENERATED / "dispatch"
DISPATCH_DATA_OUT = GENERATED / "dispatch_data"
STATS_OUT = GENERATED / "statistics"
TABLE_OUT = GENERATED / "tables"
OP_DATA = RESULTS / "paper_ready" / "operation_effect_figures"

WORKFLOW_TOTALS = {"static": 41, "dynamic": 48, "rolling": 373}
STAGE3_ACCEPTED = {
    "MiniMax M2.5": {"static": 41, "dynamic": 43, "rolling": 367},
    "MiMo v2.5": {"static": 41, "dynamic": 48, "rolling": 368},
    "Claude Haiku 4.5": {"static": 41, "dynamic": 41, "rolling": 370},
}
FAILURES = {
    "MiniMax M2.5": {"wrong_tool_order": 4, "missing_required_tool": 3, "missing_eval_ref": 4},
    "MiMo v2.5": {"wrong_tool_order": 0, "missing_required_tool": 0, "missing_eval_ref": 5},
    "Claude Haiku 4.5": {"wrong_tool_order": 7, "missing_required_tool": 3, "missing_eval_ref": 0},
}

FAMILY_LABELS = {
    "constant_release": "Constant",
    "inflow_piecewise_constant_release": "Inflow-PWC",
    "inflow_linear_release": "Inflow-Linear",
    "storage_piecewise_constant_release": "Storage-PWC",
    "storage_nonlinear_release": "Storage-NL",
    "joint_driven_release": "Joint-Driven",
}
FAMILY_ORDER = list(FAMILY_LABELS)
FAMILY_COLORS = ["#4575b4", "#1a9850", "#d73027", "#984ea3", "#f46d43", "#8c510a"]
FAMILY_STYLES = ["-", "--", "-.", ":", (0, (4, 1, 1, 1)), (0, (5, 2))]

COMMAND_LABELS = {
    "D1_release_cap_adjustment": "Cap release",
    "D2_terminal_target_lowering": "Lower target",
    "D3_target_deadline_compression": "Shorter horizon",
    "D4_conservative_risk_buffer": "Safety buffer",
}
COMMAND_ORDER = list(COMMAND_LABELS)

C_INFLOW = "#000000"
C_FORECAST = "#d6604d"
C_RELEASE = "#1a9850"
C_LEVEL = "#000000"
C_LIMIT = "#b2182b"
C_REPLAN = "#d95f02"
C_RETAIN = "#7570b3"
C_GRAY = "#8d99ae"


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif"],
            "font.size": 13,
            "axes.titlesize": 13,
            "axes.labelsize": 13,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "figure.dpi": 150,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.28,
            "grid.linestyle": "--",
            "axes.axisbelow": True,
        }
    )


def ensure_dirs() -> None:
    DISPATCH_OUT.mkdir(parents=True, exist_ok=True)
    DISPATCH_DATA_OUT.mkdir(parents=True, exist_ok=True)
    STATS_OUT.mkdir(parents=True, exist_ok=True)
    TABLE_OUT.mkdir(parents=True, exist_ok=True)


def savefig(fig: plt.Figure, name: str, category: str = "dispatch") -> None:
    ensure_dirs()
    out_dir = STATS_OUT if category == "statistics" else DISPATCH_OUT
    for ext in ("pdf", "png"):
        dpi = 600 if ext == "png" else None
        fig.savefig(out_dir / f"{name}.{ext}", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_dir / name}.pdf / .png")


def bool_count(series: pd.Series) -> int:
    return series.astype(str).str.lower().eq("true").sum()


def read_csv(rel: str | Path, **kwargs) -> pd.DataFrame:
    path = ROOT / rel if not Path(rel).is_absolute() else Path(rel)
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, **kwargs)


def parse_stage_hour(stage: str) -> int:
    return int(str(stage).replace("rolling_", "").replace("h", ""))


def load_processed_event(event_id: int | str) -> pd.DataFrame:
    path = ROOT / "data" / "processed" / "flood_event" / f"{event_id}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, parse_dates=["time"])
    return df.rename(columns={"inflow": "inflow_observed", "level": "level_state"})


def format_time_axis(ax) -> None:
    xmin, xmax = ax.get_xlim()
    span_days = max(xmax - xmin, 1e-9)
    if span_days > 4:
        locator = mdates.DayLocator(interval=max(1, int(round(span_days / 5))))
    elif span_days > 1.5:
        locator = mdates.HourLocator(interval=12)
    else:
        locator = mdates.HourLocator(interval=6)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def draw_time_step_grid(ax, times: pd.Series, *, every: int = 1) -> None:
    if len(times) == 0:
        return
    for i, tick in enumerate(times):
        if i == 0 or i % every != 0:
            continue
        ax.axvline(tick, color="#c7c7c7", lw=0.45, alpha=0.55, zorder=-2)


def load_static_instruction() -> pd.DataFrame:
    return read_csv("experiments/results/stage1_instruction_static/results.csv")


def load_dynamic_command() -> pd.DataFrame:
    return read_csv("experiments/results/stage1_dynamic_command_intervention/results.csv")


def load_stage1_dynamic() -> pd.DataFrame:
    return read_csv("experiments/results/stage1/dynamic/stage_results.csv")


def load_stage1_rolling() -> pd.DataFrame:
    return read_csv("experiments/results/stage1/rolling/stage_results.csv")


def load_static_operation_timeseries() -> pd.DataFrame:
    return read_csv(OP_DATA / "static_event_timeseries_all.csv", parse_dates=["time"])


def load_rolling_operation_timeseries() -> pd.DataFrame:
    return read_csv(OP_DATA / "rolling_event_timeseries_all.csv", parse_dates=["time"])


def command_stage_to_base_stage(checkpoint_id: str) -> str:
    if str(checkpoint_id) == "T2_peak":
        return "T2"
    return str(checkpoint_id)
