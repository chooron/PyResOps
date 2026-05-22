"""
Figure 5. Component ablation: text-only / tool-only / tool-and-contract conditions.

Grouped bar chart comparing five metrics across the three ablation conditions.
Data from: experiments/results/paper_ready/paper_ready_main_tables/table4_component_ablation.csv
           (ALL workflow rows only)

Output: docs/paper/figures/fig05_component_ablation.{pdf,png}
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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

C_TEXT = "#b2b2b2"
C_TOOL = "#d6604d"
C_TC   = "#1a9641"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Data — ALL rows from table4_component_ablation.csv
# ---------------------------------------------------------------------------
# Metrics: format_valid, tool_grounded_success, eval_ref_valid, protocol_adh, hard_viol_count
metrics = [
    "Format\nvalid",
    "Tool-grounded\nsuccess",
    "Eval-ref\nvalid",
    "Protocol\nadherence",
    "Hard-safety\nviolations",
]

# B2 (text-only, n=40): format=1.0, tool_grounded=0.0, eval_ref=0.0, protocol=N/A→0, hard=0
# B3 (tool-only, n=32): all = 0.8438 except hard=0
# B4 (tool+contract, n=40): all = 1.0 except hard=0
text_only    = [100.0,   0.0,   0.0,   0.0,  0.0]
tool_only    = [ 84.38, 84.38, 84.38, 84.38,  0.0]
tool_contract= [100.0, 100.0, 100.0, 100.0,  0.0]

x = np.arange(len(metrics))
width = 0.25

fig, ax = plt.subplots(figsize=(8.0, 4.0))

bars_t  = ax.bar(x - width,     text_only,     width, label="Text-only (n=40)",
                 color=C_TEXT, alpha=0.9)
bars_b3 = ax.bar(x,             tool_only,     width, label="Tool-only (n=32)",
                 color=C_TOOL, alpha=0.9)
bars_b4 = ax.bar(x + width,     tool_contract, width, label="Tool-and-contract (n=40)",
                 color=C_TC,   alpha=0.9)

ax.set_ylim(-5, 120)
ax.set_ylabel("Rate (%) / Count")
ax.set_xticks(x)
ax.set_xticklabels(metrics)
ax.legend(loc="upper right", framealpha=0.9)

# Annotate B3 and B4 bars for key metrics
for i, (b3_val, b4_val) in enumerate(zip(tool_only, tool_contract)):
    if i < 4:  # skip hard violations column
        ax.text(x[i],         b3_val + 1.5, f"{b3_val:.0f}%",
                ha="center", va="bottom", fontsize=7, color=C_TOOL)
        ax.text(x[i] + width, b4_val + 1.5, f"{b4_val:.0f}%",
                ha="center", va="bottom", fontsize=7, color=C_TC, fontweight="bold")

# Annotate text-only format=100% and tool-grounded=0%
ax.text(x[0] - width, text_only[0] + 1.5, "100%",
        ha="center", va="bottom", fontsize=7, color="gray")
ax.text(x[1] - width, 2.5, "0%",
        ha="center", va="bottom", fontsize=7, color="gray")

# Arrows showing incremental gain
ax.annotate("", xy=(x[1], 88), xytext=(x[1] - width - 0.02, 5),
            arrowprops=dict(arrowstyle="->", color="#555555", lw=1.2))
ax.text(x[1] - 0.22, 50, "+tool\naccess", fontsize=7, color="#555555", ha="center")

ax.annotate("", xy=(x[1] + width, 103), xytext=(x[1] + 0.02, 88),
            arrowprops=dict(arrowstyle="->", color="#555555", lw=1.2))
ax.text(x[1] + 0.38, 96, "+workflow\nrules", fontsize=7, color="#555555", ha="center")

# Hard-violations note
ax.text(x[4], 5, "All zero", ha="center", va="bottom", fontsize=7,
        color="gray", style="italic")

fig.tight_layout(pad=1.5)

for ext in ("pdf", "png"):
    path = os.path.join(OUT_DIR, f"fig05_component_ablation.{ext}")
    fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
    print(f"Saved: {path}")
plt.close(fig)
