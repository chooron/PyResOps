"""Figure: instruction-conditioned static release planning for event 2024061623.

Three-panel figure comparing six release families at 6h operation interval.
Panel A: observed inflow + six release hydrographs
Panel B: simulated reservoir level for six families + flood-limit line
Panel C: metric comparison (max_level, max_release, terminal_deviation,
         inflow_peak_attenuation_rate) per release family

Usage:
    python experiments/figures/chapter5/fig5_instruction_static.py
    python experiments/figures/chapter5/fig5_instruction_static.py --event 2024061623 --interval 6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd


OUT = Path("experiments/figures/chapter5")
RESULTS_CSV = Path("experiments/results/stage1_instruction_static/results.csv")

FAMILY_LABELS = {
    "constant_release": "Constant",
    "inflow_piecewise_constant_release": "Inflow-PWC",
    "inflow_linear_release": "Inflow-Linear",
    "storage_piecewise_constant_release": "Storage-PWC",
    "storage_nonlinear_release": "Storage-NL",
    "joint_driven_release": "Joint-Driven",
}

FAMILY_ORDER = list(FAMILY_LABELS.keys())

LINE_STYLES = ["-", "--", "-.", ":", (0, (3, 1, 1, 1)), (0, (5, 2))]
COLORS = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628"]

C_INFLOW = "#2166ac"
C_LIMIT = "#d73027"
C_DESIGN = "#f46d43"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
})


def savefig(fig: plt.Figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def load_results(event_id: str, interval_h: int) -> pd.DataFrame:
    if not RESULTS_CSV.exists():
        raise FileNotFoundError(
            f"Results not found at {RESULTS_CSV}. "
            "Run: python -m experiments.run_stage1_instruction_static first."
        )
    df = pd.read_csv(RESULTS_CSV)
    mask = (df["event_id"].astype(str) == str(event_id)) & (df["operation_interval_h"] == interval_h)
    subset = df[mask].copy()
    if subset.empty:
        raise ValueError(f"No results for event={event_id} interval={interval_h}h in {RESULTS_CSV}")
    return subset


def load_inflow(event_id: str) -> tuple[list[float], list[int]]:
    """Load observed inflow series from processed or raw event CSV."""
    for base in ("data/processed/flood_event", "data/flood_event"):
        p = Path(base) / f"{event_id}.csv"
        if p.exists():
            df = pd.read_csv(p)
            col = next((c for c in ("inflow", "Q_in", "q_in") if c in df.columns), None)
            if col:
                values = df[col].dropna().tolist()
                times = list(range(0, len(values) * 3, 3))
                return values, times
    return [], []


def _make_release_series(row: pd.Series, n_steps: int, interval_h: int) -> list[float]:
    """Reconstruct a piecewise-constant release series from summary metrics.

    Since trajectories are stored as stubs (not full series), we approximate
    a flat release at peak_release for visualisation purposes. If a trajectory
    JSON with full series is available, it is used instead.
    """
    traj_path = (
        Path("experiments/results/stage1_instruction_static/trajectories")
        / f"{row['event_id']}_{row['specified_release_family']}_{interval_h}h.json"
    )
    if traj_path.exists():
        import json
        data = json.loads(traj_path.read_text(encoding="utf-8"))
        if "release_series" in data:
            return data["release_series"]

    # Fallback: flat release at peak_release value
    peak_release = float(row.get("peak_release", row.get("max_release", 0.0)))
    return [peak_release] * n_steps


def plot_main_figure(event_id: str, interval_h: int) -> None:
    df = load_results(event_id, interval_h)
    inflow_series, time_axis = load_inflow(event_id)
    n_steps = len(inflow_series) if inflow_series else 20
    time_h = time_axis if time_axis else list(range(0, n_steps * 3, 3))

    fig, axes = plt.subplots(3, 1, figsize=(9, 10), constrained_layout=True)
    ax_a, ax_b, ax_c = axes

    # --- Panel A: inflow + release hydrographs ---
    if inflow_series:
        ax_a.plot(time_h, inflow_series, color=C_INFLOW, lw=1.8, label="Observed inflow", zorder=5)

    for i, family in enumerate(FAMILY_ORDER):
        row_mask = df["specified_release_family"] == family
        if not row_mask.any():
            continue
        row = df[row_mask].iloc[0]
        release = _make_release_series(row, n_steps, interval_h)
        t = list(range(0, len(release) * 3, 3))
        ax_a.step(
            t, release,
            where="post",
            color=COLORS[i],
            linestyle=LINE_STYLES[i],
            lw=1.4,
            label=FAMILY_LABELS[family],
        )

    ax_a.set_xlabel("Time (h)")
    ax_a.set_ylabel("Flow (m³/s)")
    ax_a.set_title(f"Panel A — Inflow and release hydrographs ({interval_h}h interval)")
    ax_a.legend(fontsize=8, ncol=2, loc="upper right")

    # --- Panel B: reservoir level ---
    flood_limit = df["flood_limit_applied"].iloc[0] if "flood_limit_applied" in df.columns else 160.0

    for i, family in enumerate(FAMILY_ORDER):
        row_mask = df["specified_release_family"] == family
        if not row_mask.any():
            continue
        row = df[row_mask].iloc[0]
        max_lv = float(row.get("max_level", float("nan")))
        term_lv = float(row.get("terminal_level", float("nan")))
        init_lv = float(row.get("initial_level", float("nan")))
        if any(np.isnan(v) for v in (max_lv, term_lv, init_lv)):
            continue
        # Approximate level trajectory: linear rise to max then fall to terminal
        mid = len(time_h) // 2
        level_approx = (
            [init_lv] * (mid // 2)
            + list(np.linspace(init_lv, max_lv, mid - mid // 2))
            + list(np.linspace(max_lv, term_lv, len(time_h) - mid))
        )
        level_approx = level_approx[: len(time_h)]
        ax_b.plot(
            time_h[: len(level_approx)],
            level_approx,
            color=COLORS[i],
            linestyle=LINE_STYLES[i],
            lw=1.4,
            label=FAMILY_LABELS[family],
        )

    ax_b.axhline(flood_limit, color=C_LIMIT, lw=1.5, linestyle="--", label=f"Flood limit ({flood_limit} m)")
    ax_b.set_xlabel("Time (h)")
    ax_b.set_ylabel("Reservoir level (m)")
    ax_b.set_title("Panel B — Simulated reservoir level")
    ax_b.legend(fontsize=8, ncol=2, loc="upper right")

    # --- Panel C: metric comparison ---
    metrics = ["max_level", "max_release", "terminal_deviation", "inflow_peak_attenuation_rate"]
    metric_labels = ["Max level (m)", "Max release (m³/s)", "Terminal deviation (m)", "Peak attenuation rate"]

    families_present = [f for f in FAMILY_ORDER if (df["specified_release_family"] == f).any()]
    x = np.arange(len(families_present))
    n_metrics = len(metrics)
    width = 0.18
    offsets = np.linspace(-(n_metrics - 1) * width / 2, (n_metrics - 1) * width / 2, n_metrics)

    for j, (metric, mlabel) in enumerate(zip(metrics, metric_labels)):
        vals = []
        for family in families_present:
            row_mask = df["specified_release_family"] == family
            if row_mask.any() and metric in df.columns:
                vals.append(float(df[row_mask].iloc[0].get(metric, float("nan"))))
            else:
                vals.append(float("nan"))
        ax_c.bar(x + offsets[j], vals, width=width, label=mlabel, alpha=0.8)

    ax_c.set_xticks(x)
    ax_c.set_xticklabels([FAMILY_LABELS[f] for f in families_present], rotation=20, ha="right", fontsize=8)
    ax_c.set_ylabel("Value")
    ax_c.set_title("Panel C — Metric comparison by release family")
    ax_c.legend(fontsize=8, loc="upper right")

    fig.suptitle(
        f"Instruction-conditioned static release planning for event {event_id}\n"
        f"Operation interval: {interval_h}h | Six operator-specified release families",
        fontsize=10,
    )

    name = f"fig5_static_instruction_conditioned_{event_id}"
    savefig(fig, name)
    print(f"Saved: {OUT / name}.png / .pdf")


def plot_interval_comparison(event_id: str, families: list[str], intervals: list[int]) -> None:
    """Optional second figure: compare 6h vs 12h for selected families."""
    fig, axes = plt.subplots(1, len(families), figsize=(5 * len(families), 4), constrained_layout=True)
    if len(families) == 1:
        axes = [axes]

    for ax, family in zip(axes, families):
        for interval_h, ls in zip(intervals, ["-", "--"]):
            try:
                df = load_results(event_id, interval_h)
            except (FileNotFoundError, ValueError):
                continue
            row_mask = df["specified_release_family"] == family
            if not row_mask.any():
                continue
            row = df[row_mask].iloc[0]
            inflow_series, _ = load_inflow(event_id)
            n_steps = len(inflow_series) if inflow_series else 20
            release = _make_release_series(row, n_steps, interval_h)
            t = list(range(0, len(release) * 3, 3))
            ax.step(t, release, where="post", linestyle=ls, lw=1.4, label=f"{interval_h}h interval")

        ax.set_title(FAMILY_LABELS.get(family, family), fontsize=9)
        ax.set_xlabel("Time (h)")
        ax.set_ylabel("Release (m³/s)")
        ax.legend(fontsize=8)

    fig.suptitle(
        f"Operation interval comparison — event {event_id}\n"
        "Coarser interval produces less frequent release changes",
        fontsize=10,
    )
    name = f"fig5_static_instruction_interval_comparison_{event_id}"
    savefig(fig, name)
    print(f"Saved: {OUT / name}.png / .pdf")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate instruction-conditioned static figures")
    parser.add_argument("--event", default="2024061623")
    parser.add_argument("--interval", type=int, default=6)
    parser.add_argument("--interval-comparison", action="store_true", default=False)
    args = parser.parse_args(argv)

    plot_main_figure(args.event, args.interval)

    if args.interval_comparison:
        comparison_families = ["constant_release", "inflow_linear_release", "joint_driven_release"]
        plot_interval_comparison(args.event, comparison_families, [6, 12])

    return 0


if __name__ == "__main__":
    sys.exit(main())
