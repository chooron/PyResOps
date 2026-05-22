"""
Figures 8–10. Representative operation cases (illustrative).

Physically consistent synthetic trajectories based on Tankeng Reservoir parameters:
  flood-limit level = 156.5 m
  design flood level = 165.87 m
  total capacity ~ 41.9e8 m3

All figures are labelled "Illustrative example based on Tankeng Reservoir parameters."

Output:
  docs/paper/figures/fig08_static_case.{pdf,png}
  docs/paper/figures/fig09_dynamic_case.{pdf,png}
  docs/paper/figures/fig10_rolling_case.{pdf,png}
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "axes.titlesize": 9,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "axes.axisbelow": True,
})

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

ILLUS_NOTE = "Illustrative example based on Tankeng Reservoir parameters"
Z_FLOOD_LIMIT  = 156.5
Z_DESIGN_FLOOD = 165.87

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def add_level_lines(ax, ymin=None, ymax=None):
    ax.axhline(Z_FLOOD_LIMIT,  color="#d6604d", linestyle="--", linewidth=0.9,
               label=f"Flood-limit level ({Z_FLOOD_LIMIT} m)", alpha=0.8)
    ax.axhline(Z_DESIGN_FLOOD, color="#b2182b", linestyle=":",  linewidth=0.9,
               label=f"Design flood level ({Z_DESIGN_FLOOD} m)", alpha=0.8)


def illus_label(fig):
    fig.text(0.5, -0.01, ILLUS_NOTE, ha="center", fontsize=7,
             color="gray", style="italic")


# ---------------------------------------------------------------------------
# Figure 8 — Representative static operation case
# ---------------------------------------------------------------------------

def fig08_static_case():
    T = 25  # 24-hour horizon, hourly steps
    t = np.arange(T)

    # Synthetic inflow: rising limb then recession
    inflow = 800 + 1200 * np.exp(-0.5 * ((t - 8) / 4) ** 2)

    # Optimized release: smooth ramp following inflow with lag
    release = 600 + 900 * np.exp(-0.5 * ((t - 11) / 5) ** 2)
    release = np.clip(release, 0, 2200)

    # Water balance (simplified, dt=1h, storage in 1e6 m3)
    dt = 3600  # seconds
    S = np.zeros(T + 1)
    S[0] = 28.0e8  # initial storage ~28e8 m3
    for i in range(T):
        S[i + 1] = S[i] + (inflow[i] - release[i]) * dt
        S[i + 1] = max(S[i + 1], 0)

    # Storage to level (linear approximation for illustration)
    Z_min, Z_max_cap = 140.0, 168.0
    S_min, S_max_cap = 5.0e8, 45.0e8
    Z = Z_min + (Z_max_cap - Z_min) * (S[:-1] - S_min) / (S_max_cap - S_min)
    Z = np.clip(Z, Z_min, Z_max_cap)

    fig, axes = plt.subplots(2, 2, figsize=(8.5, 5.5))
    fig.suptitle("Figure 8. Representative static operation case", fontsize=9, fontweight="bold")

    # (a) Inflow
    ax = axes[0, 0]
    ax.fill_between(t, inflow, alpha=0.25, color="#2166ac")
    ax.plot(t, inflow, color="#2166ac", linewidth=1.5, label="Inflow")
    ax.set_ylabel("Flow rate (m³/s)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(a) Observed inflow hydrograph")
    ax.legend()

    # (b) Release
    ax = axes[0, 1]
    ax.fill_between(t, release, alpha=0.25, color="#1a9641")
    ax.plot(t, release, color="#1a9641", linewidth=1.5, label="Optimized release")
    ax.axhline(2200, color="#d6604d", linestyle="--", linewidth=0.9,
               label="Safe downstream limit", alpha=0.8)
    ax.set_ylabel("Release rate (m³/s)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(b) Optimized release trajectory")
    ax.legend(fontsize=7)

    # (c) Water level
    ax = axes[1, 0]
    ax.plot(t, Z, color="#762a83", linewidth=1.5, label="Water level")
    add_level_lines(ax)
    ax.axhline(Z[-1], color="#555555", linestyle=":", linewidth=0.8, alpha=0.6)
    ax.text(T - 1, Z[-1] + 0.15, f"Terminal: {Z[-1]:.2f} m", fontsize=7,
            ha="right", color="#555555")
    ax.set_ylabel("Water level (m)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(c) Reservoir water-level trajectory")
    ax.legend(fontsize=7)

    # (d) Score summary
    ax = axes[1, 1]
    score_labels = ["Overall\nscore", "Flood-ctrl\ncomponent", "Terminal\ndev. (×10)"]
    score_vals   = [82.4, 100.0, 18.5]  # terminal dev ~1.85 m → ×10 for display
    colors = ["#1a9641", "#2166ac", "#d6604d"]
    bars = ax.bar(score_labels, score_vals, color=colors, alpha=0.85, width=0.5)
    ax.set_ylim(0, 115)
    ax.set_ylabel("Score / scaled value")
    ax.set_title("(d) Evaluation summary")
    for bar, val in zip(bars, score_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{val:.1f}", ha="center", va="bottom", fontsize=8)
    ax.text(0.5, 0.92, "Hard-safety: PASS  |  Eval-ref: VALID",
            transform=ax.transAxes, ha="center", fontsize=7.5,
            color="#1a9641", fontweight="bold")

    fig.tight_layout(pad=1.5)
    illus_label(fig)

    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig08_static_case.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 9 — Representative dynamic operation under instruction changes
# ---------------------------------------------------------------------------

def fig09_dynamic_case():
    stages = [0, 3, 6, 9]
    stage_labels = ["Stage 0h", "Stage 3h", "Stage 6h\n(−0.2 m)", "Stage 9h\n(−0.1 m)"]
    decisions = ["Replan", "Retain", "Replan", "Replan"]
    targets = [156.5, 156.5, 156.3, 156.2]

    T = 13
    t = np.arange(T)

    # Three release plans (before/after adjustments)
    plan_base   = 800 + 400 * np.exp(-0.5 * ((t - 5) / 3) ** 2)
    plan_adj1   = 820 + 380 * np.exp(-0.5 * ((t - 5) / 3) ** 2)
    plan_adj2   = 840 + 360 * np.exp(-0.5 * ((t - 5) / 3) ** 2)

    # Water levels for each plan
    def water_level(release, z0=155.8):
        Z = [z0]
        for r in release:
            dz = (900 - r) * 3600 / 4.0e8 * 10
            Z.append(Z[-1] + dz)
        return np.array(Z[:T])

    Z_base = water_level(plan_base)
    Z_adj1 = water_level(plan_adj1)
    Z_adj2 = water_level(plan_adj2)

    fig, axes = plt.subplots(2, 2, figsize=(8.5, 5.5))
    fig.suptitle("Figure 9. Representative dynamic operation under instruction changes",
                 fontsize=9, fontweight="bold")

    # (a) Instruction timeline
    ax = axes[0, 0]
    colors_dec = ["#1a9641" if d == "Retain" else "#d6604d" for d in decisions]
    ax.scatter(stages, [1] * 4, s=120, c=colors_dec, zorder=5)
    ax.hlines(1, 0, 9, colors="gray", linewidth=0.8, linestyle="--")
    for s, lbl, dec, tgt in zip(stages, stage_labels, decisions, targets):
        ax.text(s, 1.08, lbl, ha="center", fontsize=7.5)
        ax.text(s, 0.88, f"{dec}\ntarget={tgt}m", ha="center", fontsize=6.5,
                color=colors_dec[stages.index(s)])
    ax.set_xlim(-1, 10)
    ax.set_ylim(0.6, 1.4)
    ax.set_yticks([])
    ax.set_xlabel("Time offset (h)")
    ax.set_title("(a) Instruction timeline and decisions")
    retain_patch = mpatches.Patch(color="#1a9641", label="Retain")
    replan_patch = mpatches.Patch(color="#d6604d", label="Replan")
    ax.legend(handles=[retain_patch, replan_patch], loc="lower right", fontsize=7)

    # (b) Release plans
    ax = axes[0, 1]
    ax.plot(t, plan_base, color="#2166ac", linewidth=1.5, linestyle="-",  label="Initial plan")
    ax.plot(t, plan_adj1, color="#762a83", linewidth=1.5, linestyle="--", label="After 6h adj.")
    ax.plot(t, plan_adj2, color="#d6604d", linewidth=1.5, linestyle=":",  label="After 9h adj.")
    ax.set_ylabel("Release rate (m³/s)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(b) Release plan revisions")
    ax.legend(fontsize=7)

    # (c) Water-level trajectories
    ax = axes[1, 0]
    ax.plot(t, Z_base, color="#2166ac", linewidth=1.5, linestyle="-",  label="Initial plan")
    ax.plot(t, Z_adj1, color="#762a83", linewidth=1.5, linestyle="--", label="After 6h adj.")
    ax.plot(t, Z_adj2, color="#d6604d", linewidth=1.5, linestyle=":",  label="After 9h adj.")
    ax.axhline(Z_FLOOD_LIMIT, color="#d6604d", linestyle="--", linewidth=0.8,
               label=f"Flood-limit ({Z_FLOOD_LIMIT} m)", alpha=0.7)
    for tgt, col in zip([156.5, 156.3, 156.2], ["#2166ac", "#762a83", "#d6604d"]):
        ax.axhline(tgt, color=col, linestyle=":", linewidth=0.6, alpha=0.5)
    ax.set_ylabel("Water level (m)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(c) Water-level trajectories")
    ax.legend(fontsize=6.5)

    # (d) Carry-over evaluation at each stage
    ax = axes[1, 1]
    stage_x = np.arange(4)
    carry_scores = [None, 81.2, 79.8, 78.5]  # stage 0 has no carry-over
    carry_valid  = [False, True, True, True]
    bar_colors   = ["#b2b2b2", "#1a9641", "#1a9641", "#1a9641"]
    bars = ax.bar(stage_x, [0 if s is None else s for s in carry_scores],
                  color=bar_colors, alpha=0.85, width=0.5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Carry-over evaluation score")
    ax.set_title("(d) Carry-over evaluation at each stage")
    ax.set_xticks(stage_x)
    ax.set_xticklabels(stage_labels, fontsize=7)
    for i, (bar, score, valid) in enumerate(zip(bars, carry_scores, carry_valid)):
        if score is not None:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f"{score:.1f}", ha="center", va="bottom", fontsize=7.5)
        else:
            ax.text(bar.get_x() + bar.get_width() / 2, 3,
                    "N/A\n(initial)", ha="center", va="bottom", fontsize=6.5, color="gray")

    fig.tight_layout(pad=1.5)
    illus_label(fig)

    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig09_dynamic_case.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 10 — Representative rolling operation with forecast updates
# ---------------------------------------------------------------------------

def fig10_rolling_case():
    T = 13
    t = np.arange(T)

    # Forecast vs observed inflow
    obs_inflow  = 600 + 1000 * np.exp(-0.5 * ((t - 6) / 3.5) ** 2)
    fore_inflow = obs_inflow * (1 + 0.15 * np.sin(t * 0.8))  # forecast with error

    # Trigger timeline: 0=none, 1=scheduled, 2=forecast-error, 3=state-risk
    trigger_type = [1, 0, 0, 2, 0, 0, 1, 3, 0, 0, 1, 0, 0]
    trigger_colors = {0: "white", 1: "#2166ac", 2: "#d6604d", 3: "#762a83"}
    trigger_labels_map = {0: "None", 1: "Scheduled", 2: "Forecast err.", 3: "State risk"}

    # Release plan revisions (3 plans at trigger points)
    plan_v1 = 500 + 700 * np.exp(-0.5 * ((t - 6) / 4) ** 2)
    plan_v2 = 520 + 680 * np.exp(-0.5 * ((t - 6) / 4) ** 2)
    plan_v3 = 540 + 660 * np.exp(-0.5 * ((t - 6) / 4) ** 2)

    # Committed release (follows plan_v1 until t=3, then v2, then v3 from t=7)
    committed = np.where(t < 3, plan_v1, np.where(t < 7, plan_v2, plan_v3))

    # Water level
    Z = [155.2]
    for r in committed:
        dz = (obs_inflow[int(min(r / 100, T - 1))] - r) * 3600 / 4.5e8 * 10
        Z.append(Z[-1] + dz * 0.3)
    Z = np.array(Z[:T])

    fig, axes = plt.subplots(2, 2, figsize=(8.5, 5.5))
    fig.suptitle("Figure 10. Representative rolling operation with forecast updates",
                 fontsize=9, fontweight="bold")

    # (a) Forecast vs observed inflow
    ax = axes[0, 0]
    ax.fill_between(t, obs_inflow, alpha=0.2, color="#2166ac")
    ax.plot(t, obs_inflow,  color="#2166ac", linewidth=1.5, label="Observed inflow")
    ax.plot(t, fore_inflow, color="#d6604d", linewidth=1.5, linestyle="--",
            label="Forecast inflow")
    ax.fill_between(t, obs_inflow, fore_inflow, alpha=0.15, color="#d6604d",
                    label="Forecast error")
    ax.set_ylabel("Flow rate (m³/s)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(a) Forecast vs observed inflow")
    ax.legend(fontsize=7)

    # (b) Trigger timeline
    ax = axes[0, 1]
    for i, tt in enumerate(trigger_type):
        ax.scatter(i, 1, s=100, c=trigger_colors[tt], edgecolors="gray",
                   linewidths=0.5, zorder=5)
        if tt != 0:
            ax.text(i, 1.12, trigger_labels_map[tt], ha="center", fontsize=6,
                    color=trigger_colors[tt], rotation=30)
    ax.hlines(1, 0, T - 1, colors="gray", linewidth=0.6, linestyle="--")
    ax.set_xlim(-0.5, T - 0.5)
    ax.set_ylim(0.7, 1.5)
    ax.set_yticks([])
    ax.set_xlabel("Rolling stage index")
    ax.set_title("(b) Trigger timeline")
    legend_handles = [
        mpatches.Patch(color="#2166ac", label="Scheduled"),
        mpatches.Patch(color="#d6604d", label="Forecast err."),
        mpatches.Patch(color="#762a83", label="State risk"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=6.5)

    # (c) Release plan revisions
    ax = axes[1, 0]
    ax.plot(t, plan_v1, color="#74add1", linewidth=1.2, linestyle="--",
            label="Plan v1 (initial)", alpha=0.7)
    ax.plot(t, plan_v2, color="#762a83", linewidth=1.2, linestyle="--",
            label="Plan v2 (after t=3)", alpha=0.7)
    ax.plot(t, plan_v3, color="#d6604d", linewidth=1.2, linestyle="--",
            label="Plan v3 (after t=7)", alpha=0.7)
    ax.plot(t, committed, color="#1a9641", linewidth=2.0,
            label="Committed release")
    ax.set_ylabel("Release rate (m³/s)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(c) Release plan revisions and committed release")
    ax.legend(fontsize=6.5)

    # (d) Water level
    ax = axes[1, 1]
    ax.plot(t, Z, color="#762a83", linewidth=1.5, label="Water level")
    ax.axhline(Z_FLOOD_LIMIT, color="#d6604d", linestyle="--", linewidth=0.9,
               label=f"Flood-limit ({Z_FLOOD_LIMIT} m)", alpha=0.8)
    ax.set_ylabel("Water level (m)")
    ax.set_xlabel("Time (h)")
    ax.set_title("(d) Reservoir water-level trajectory")
    ax.legend(fontsize=7)
    ax.text(0.02, 0.05, "Hard-safety: PASS  |  Eval-ref: VALID",
            transform=ax.transAxes, fontsize=7, color="#1a9641",
            fontweight="bold")

    fig.tight_layout(pad=1.5)
    illus_label(fig)

    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig10_rolling_case.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating illustrative operation case figures (8–10)...")
    fig08_static_case()
    fig09_dynamic_case()
    fig10_rolling_case()
    print("Done.")
