"""
Figure 6. MCP-based workflow validation by scenario.

Grouped bar chart: static / dynamic / rolling / total.
Bars: acceptance rate, MCP call success rate, protocol adherence, eval-ref validity.
Data from: experiments/results/paper_ready/paper_ready_main_tables/table3_mcp_skill_main_validation.csv

Output: docs/paper/figures/fig06_workflow_validation.{pdf,png}
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

C_ACC   = "#1a9641"
C_MCP   = "#2166ac"
C_PROT  = "#762a83"
C_EVAL  = "#d6604d"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Data from table3_mcp_skill_main_validation.csv
# ---------------------------------------------------------------------------
workflows = ["Static\n(n=6)", "Dynamic\n(n=42)", "Rolling\n(n=73)", "Total\n(n=121)"]

acceptance   = [100.00, 97.62, 98.63, 98.35]
mcp_call     = [100.00, 100.00, 100.00, 100.00]
protocol_adh = [100.00, 97.62, 98.63, 98.35]
eval_ref     = [100.00, 97.62, 98.63, 98.35]

x = np.arange(len(workflows))
width = 0.18

fig, ax = plt.subplots(figsize=(8.0, 4.2))

b1 = ax.bar(x - 1.5*width, acceptance,   width, label="Acceptance rate",       color=C_ACC,  alpha=0.88)
b2 = ax.bar(x - 0.5*width, mcp_call,     width, label="MCP call success",      color=C_MCP,  alpha=0.88)
b3 = ax.bar(x + 0.5*width, protocol_adh, width, label="Protocol adherence",    color=C_PROT, alpha=0.88)
b4 = ax.bar(x + 1.5*width, eval_ref,     width, label="Eval-ref validity",     color=C_EVAL, alpha=0.88)

ax.set_ylim(88, 104)
ax.set_ylabel("Rate (%)")
ax.set_xticks(x)
ax.set_xticklabels(workflows)
ax.legend(loc="lower right", framealpha=0.9, ncol=2)

# Annotate acceptance rate bars
for i, val in enumerate(acceptance):
    ax.text(x[i] - 1.5*width, val + 0.2, f"{val:.2f}%",
            ha="center", va="bottom", fontsize=6.5, color=C_ACC)

# MCP call annotation
ax.text(0.5, 103.2, "MCP tool calls: 468 / 468 (100%)",
        transform=ax.transAxes, ha="center", va="bottom",
        fontsize=7.5, color=C_MCP,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=C_MCP, alpha=0.8))

# Hard-safety note
ax.text(0.02, 0.04, "Hard-safety violations: 0 across all 121 records",
        transform=ax.transAxes, fontsize=7, color="gray", style="italic")

fig.tight_layout(pad=1.5)

for ext in ("pdf", "png"):
    path = os.path.join(OUT_DIR, f"fig06_workflow_validation.{ext}")
    fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
    print(f"Saved: {path}")
plt.close(fig)
