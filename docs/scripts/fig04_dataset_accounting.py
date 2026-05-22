"""
Figure 4. Dataset quality and validation record accounting.

Two-panel figure:
  Left:  Horizontal stacked bar — 41 events split into strict-clean / repaired-executable.
  Right: Grouped bar — validation record counts by experiment condition.

Output: docs/paper/figures/fig04_dataset_accounting.{pdf,png}
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
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

C_CLEAN    = "#2166ac"
C_REPAIRED = "#74add1"
C_DET      = "#1a9641"
C_MCP      = "#762a83"
C_CMD      = "#d6604d"
C_ROLL     = "#f4a582"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
# Event quality (from table1_dataset_quality.csv)
strict_clean       = 29
repaired_exec      = 12
total_events       = 41

# Validation record counts
conditions   = ["Deterministic\nbaseline", "MCP-based\nworkflow", "Command-\nfollowing", "Rolling\nstages"]
record_counts = [166, 121, 40, 93]
bar_colors    = [C_DET, C_MCP, C_CMD, C_ROLL]

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(8.0, 3.2),
                                         gridspec_kw={"width_ratios": [1, 1.6]})

# --- Left: stacked horizontal bar ---
ax_left.barh(["Events"], [strict_clean], color=C_CLEAN,  label="Strict-clean (n=29)")
ax_left.barh(["Events"], [repaired_exec], left=[strict_clean],
             color=C_REPAIRED, label="Repaired-executable (n=12)")
ax_left.set_xlim(0, 50)
ax_left.set_xlabel("Number of events")
ax_left.set_title("(a) Dataset quality (41 flood events)")
ax_left.legend(loc="lower right", framealpha=0.9)
ax_left.text(strict_clean / 2, 0, "29", ha="center", va="center",
             fontsize=8, color="white", fontweight="bold")
ax_left.text(strict_clean + repaired_exec / 2, 0, "12", ha="center", va="center",
             fontsize=8, color="white", fontweight="bold")
ax_left.set_yticks([])
ax_left.grid(False)

# --- Right: grouped bar ---
x = np.arange(len(conditions))
bars = ax_right.bar(x, record_counts, color=bar_colors, alpha=0.88, width=0.55)
ax_right.set_ylabel("Records / stages")
ax_right.set_title("(b) Validation record counts by experiment")
ax_right.set_xticks(x)
ax_right.set_xticklabels(conditions)
ax_right.set_ylim(0, 210)
for bar, val in zip(bars, record_counts):
    ax_right.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 3,
                  str(val), ha="center", va="bottom", fontsize=8, fontweight="bold")

fig.tight_layout(pad=1.5)

for ext in ("pdf", "png"):
    path = os.path.join(OUT_DIR, f"fig04_dataset_accounting.{ext}")
    fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
    print(f"Saved: {path}")
plt.close(fig)
