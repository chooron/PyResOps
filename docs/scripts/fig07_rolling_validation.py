"""
Figure 7. Ten-event real-forecast rolling validation and failure taxonomy.

Two-panel figure:
  Top:    Per-event grouped bar — total stages vs successful stages.
  Bottom: Trigger distribution (stacked bar) and failure taxonomy (bar).

Data from:
  experiments/results/paper_ready/paper_ready_supplementary_tables/tableS_rolling_event_summary.csv
  experiments/results/paper_ready/paper_ready_supplementary_tables/tableS_rolling_trigger_summary.csv

Output: docs/paper/figures/fig07_rolling_validation.{pdf,png}
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
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.5,
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
    "axes.axisbelow": True,
})

C_TOTAL   = "#74add1"
C_SUCCESS = "#1a9641"
C_FAIL    = "#d6604d"
C_SCHED   = "#2166ac"
C_STATE   = "#762a83"
C_REL     = "#f4a582"
C_ABS     = "#fdae61"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Data from tableS_rolling_event_summary.csv
# ---------------------------------------------------------------------------
event_ids = [
    "2012062402", "2013100711", "2019070517", "2019071011",
    "2021052114", "2022062023", "2024061220", "2024061517",
    "2024061623", "2024072617",
]
event_labels = [e[4:8] + "-" + e[8:] for e in event_ids]  # e.g. "0624-02"
stage_counts   = [21, 7, 9, 9, 17, 11, 4, 3, 5, 7]
success_counts = [19, 7, 8, 9, 16,  9, 4, 3, 5, 7]
failure_counts = [ 2, 0, 1, 0,  1,  2, 0, 0, 0, 0]

# ---------------------------------------------------------------------------
# Data from tableS_rolling_trigger_summary.csv
# ---------------------------------------------------------------------------
trigger_labels  = ["Scheduled\n12h check", "State\nrisk", "Relative\nforecast err.", "Absolute\nforecast err."]
trigger_counts  = [64, 18, 9, 2]
trigger_success = [59, 18, 8, 2]
trigger_fail    = [ 5,  0, 1, 0]

# Failure taxonomy (from table6_rolling_10_event_validation.csv)
fail_labels = ["Hallucinated\neval-ref", "Missing\neval-ref", "Missing\nrequired tool"]
fail_counts = [4, 1, 1]

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
fig, (ax_top, ax_bot_left, ax_bot_right) = plt.subplots(
    1, 3, figsize=(11.0, 4.0),
    gridspec_kw={"width_ratios": [2.5, 1.8, 1.0]}
)
# Rearrange as 2-row layout
fig.clear()
gs = fig.add_gridspec(2, 2, hspace=0.45, wspace=0.35,
                      height_ratios=[1.2, 1.0])
ax_top   = fig.add_subplot(gs[0, :])
ax_trig  = fig.add_subplot(gs[1, 0])
ax_fail  = fig.add_subplot(gs[1, 1])

fig.set_size_inches(9.0, 5.5)

# --- Top: per-event stages ---
x = np.arange(len(event_ids))
width = 0.35
ax_top.bar(x - width/2, stage_counts,   width, label="Total stages",     color=C_TOTAL,   alpha=0.85)
ax_top.bar(x + width/2, success_counts, width, label="Successful stages", color=C_SUCCESS, alpha=0.85)
for i, (tot, suc, fail) in enumerate(zip(stage_counts, success_counts, failure_counts)):
    if fail > 0:
        ax_top.text(x[i] + width/2, suc + 0.3, f"−{fail}", ha="center",
                    va="bottom", fontsize=7, color=C_FAIL, fontweight="bold")
ax_top.set_ylabel("Stage count")
ax_top.set_title("(a) Per-event rolling stage outcomes (10 events, 93 stages total)")
ax_top.set_xticks(x)
ax_top.set_xticklabels(event_labels, rotation=30, ha="right")
ax_top.legend(loc="upper right", framealpha=0.9)
ax_top.text(0.01, 0.96,
            "87/93 successful  |  0 hard-safety violations  |  391/391 MCP tool calls",
            transform=ax_top.transAxes, fontsize=7.5, va="top",
            color="#333333",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f0f0f0", edgecolor="gray", alpha=0.8))

# --- Bottom-left: trigger distribution ---
xt = np.arange(len(trigger_labels))
ax_trig.bar(xt, trigger_success, color=C_SUCCESS, alpha=0.85, label="Successful")
ax_trig.bar(xt, trigger_fail,    bottom=trigger_success, color=C_FAIL, alpha=0.85, label="Failed")
ax_trig.set_ylabel("Stage count")
ax_trig.set_title("(b) Trigger distribution")
ax_trig.set_xticks(xt)
ax_trig.set_xticklabels(trigger_labels, fontsize=7)
ax_trig.legend(loc="upper right", fontsize=7, framealpha=0.9)
for i, (s, f) in enumerate(zip(trigger_success, trigger_fail)):
    ax_trig.text(xt[i], s + f + 0.4, str(s + f), ha="center", va="bottom", fontsize=7)

# --- Bottom-right: failure taxonomy ---
xf = np.arange(len(fail_labels))
ax_fail.bar(xf, fail_counts, color=C_FAIL, alpha=0.85, width=0.5)
ax_fail.set_ylabel("Count")
ax_fail.set_title("(c) Failure taxonomy\n(6 failed stages)")
ax_fail.set_xticks(xf)
ax_fail.set_xticklabels(fail_labels, fontsize=7)
ax_fail.set_ylim(0, 6)
for i, v in enumerate(fail_counts):
    ax_fail.text(xf[i], v + 0.1, str(v), ha="center", va="bottom", fontsize=8, fontweight="bold")
ax_fail.text(0.5, -0.28, "All failures: auditability issues\n(no hard-safety violations)",
             transform=ax_fail.transAxes, ha="center", fontsize=6.5,
             color="gray", style="italic")

for ext in ("pdf", "png"):
    path = os.path.join(OUT_DIR, f"fig07_rolling_validation.{ext}")
    fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
    print(f"Saved: {path}")
plt.close(fig)
