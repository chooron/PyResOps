"""
PyResOps paper figure generation script.

Generates publication-quality figures for the ESWA submission using
matplotlib with a clean computer-science publication style.

Usage:
    python docs/paper/figures/generate_figures.py

Output:
    docs/paper/figures/fig4_tool_use_validation.pdf
    docs/paper/figures/fig4_tool_use_validation.png
    docs/paper/figures/fig5_component_ablation.pdf
    docs/paper/figures/fig5_component_ablation.png
    docs/paper/figures/fig6_command_challenge.pdf
    docs/paper/figures/fig6_command_challenge.png
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ---------------------------------------------------------------------------
# Style configuration
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

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Color palette (consistent across all figures)
# ---------------------------------------------------------------------------
C_DET   = "#2166ac"   # deterministic / L1 — steel blue
C_L2    = "#b2b2b2"   # L2 no-tools — light gray
C_B3    = "#d6604d"   # B3 MCP no skill — orange-red
C_B4    = "#1a9641"   # B4 MCP + skill — dark green
C_STRESS = "#762a83"  # rolling stress — purple

# ---------------------------------------------------------------------------
# Figure 4 — Tool-use validation results (B4 across workflow types)
# ---------------------------------------------------------------------------

def fig4_tool_use_validation():
    """
    2×2 subplot figure showing B4 validation results across workflow types.
    Top-left:  Success rate and protocol adherence by workflow
    Top-right: Engineering quality metrics (overall score)
    Bottom-left: Terminal water-level deviation by workflow
    Bottom-right: Hard-safety breach count (all zero, reference bar)
    """
    workflows = ["Static\n(n=5)", "Dynamic\n(n=8)", "Rolling\n(n=10)", "Stress\n(n=62)"]
    x = np.arange(len(workflows))
    width = 0.35

    # --- data ---
    success_rates      = [1.00, 1.00, 1.00, 0.9839]
    protocol_adherence = [1.00, 1.00, 1.00, 0.9839]
    overall_scores     = [80.25, 77.21, 88.90, 88.89]
    terminal_devs      = [2.045, 1.076, 0.197, 0.261]
    hard_violations    = [0, 0, 0, 0]

    fig, axes = plt.subplots(2, 2, figsize=(7.5, 5.5))
    fig.suptitle(
        "Figure 4. B4 Tool-Use Validation Results Across Workflow Types",
        fontsize=9, fontweight="bold", y=1.01
    )

    # --- top-left: success rate & protocol adherence ---
    ax = axes[0, 0]
    bars1 = ax.bar(x - width/2, [v * 100 for v in success_rates],
                   width, label="Success rate", color=C_B4, alpha=0.85)
    bars2 = ax.bar(x + width/2, [v * 100 for v in protocol_adherence],
                   width, label="Protocol adherence", color=C_DET, alpha=0.85)
    ax.set_ylim(90, 102)
    ax.set_ylabel("Rate (%)")
    ax.set_title("(a) Success Rate and Protocol Adherence")
    ax.set_xticks(x)
    ax.set_xticklabels(workflows)
    ax.legend(loc="lower right")
    # annotate the stress bar
    ax.annotate("98.39%", xy=(x[3] - width/2, 98.39 + 0.2),
                ha="center", va="bottom", fontsize=7, color=C_B4)

    # --- top-right: overall engineering score ---
    ax = axes[0, 1]
    colors = [C_B4, C_B4, C_B4, C_STRESS]
    bars = ax.bar(x, overall_scores, color=colors, alpha=0.85, width=0.5)
    ax.set_ylim(60, 100)
    ax.set_ylabel("Overall Score (0–100)")
    ax.set_title("(b) Engineering Quality Score (Mean)")
    ax.set_xticks(x)
    ax.set_xticklabels(workflows)
    for bar, val in zip(bars, overall_scores):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.1f}", ha="center", va="bottom", fontsize=7)
    # flood control reference line
    ax.axhline(100, color="gray", linestyle=":", linewidth=0.8, alpha=0.6)
    ax.text(3.4, 100.5, "Flood ctrl = 100", fontsize=6.5, color="gray", ha="right")

    # --- bottom-left: terminal water-level deviation ---
    ax = axes[1, 0]
    bars = ax.bar(x, terminal_devs, color=[C_B4, C_B4, C_B4, C_STRESS],
                  alpha=0.85, width=0.5)
    ax.set_ylabel("Terminal Level Deviation (m)")
    ax.set_title("(c) Mean Terminal Water-Level Deviation")
    ax.set_xticks(x)
    ax.set_xticklabels(workflows)
    for bar, val in zip(bars, terminal_devs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03,
                f"{val:.3f}", ha="center", va="bottom", fontsize=7)

    # --- bottom-right: hard-safety violations ---
    ax = axes[1, 1]
    bars = ax.bar(x, hard_violations, color=C_B4, alpha=0.85, width=0.5)
    ax.set_ylim(0, 3)
    ax.set_ylabel("Hard-Safety Violations (count)")
    ax.set_title("(d) Hard-Safety Breach Count")
    ax.set_xticks(x)
    ax.set_xticklabels(workflows)
    ax.text(1.5, 1.5, "Zero violations\nacross all conditions",
            ha="center", va="center", fontsize=8, color="gray",
            style="italic")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig4_tool_use_validation.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 5 — Component ablation (L2 vs B3 vs B4)
# ---------------------------------------------------------------------------

def fig5_component_ablation():
    """
    1×3 subplot comparing L2, B3, B4 on key metrics.
    Left:   Success rate by workflow
    Center: Evaluation-reference validity by workflow
    Right:  Protocol adherence by workflow
    """
    conditions = ["L2\n(no tools)", "B3\n(MCP, no skill)", "B4\n(MCP + skill)"]
    colors = [C_L2, C_B3, C_B4]
    x = np.arange(len(conditions))
    width = 0.22

    # per-workflow data (static / dynamic / rolling)
    # success rate
    sr_static  = [1.00, 0.60, 1.00]
    sr_dynamic = [1.00, 1.00, 1.00]
    sr_rolling = [1.00, 0.50, 1.00]

    # evaluation-reference validity
    ev_static  = [0.00, 0.60, 1.00]
    ev_dynamic = [0.00, 1.00, 1.00]
    ev_rolling = [0.00, 0.50, 1.00]

    # protocol adherence
    pa_static  = [1.00, 0.60, 1.00]
    pa_dynamic = [1.00, 1.00, 1.00]
    pa_rolling = [1.00, 0.50, 1.00]

    fig, axes = plt.subplots(1, 3, figsize=(9, 3.8), sharey=False)
    fig.suptitle(
        "Figure 5. Component Ablation: L2 (No Tools) vs B3 (MCP, No Skill) vs B4 (MCP + Skill)",
        fontsize=9, fontweight="bold", y=1.03
    )

    workflow_labels = ["Static", "Dynamic", "Rolling"]
    x_wf = np.arange(len(workflow_labels))

    def grouped_bars(ax, data_per_condition, title, ylabel):
        for i, (vals, color, label) in enumerate(zip(data_per_condition, colors, conditions)):
            offset = (i - 1) * width
            bars = ax.bar(x_wf + offset, [v * 100 for v in vals],
                          width, label=label, color=color, alpha=0.85)
        ax.set_ylim(0, 115)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.set_xticks(x_wf)
        ax.set_xticklabels(workflow_labels)
        ax.legend(loc="upper right", fontsize=7)

    grouped_bars(
        axes[0],
        [sr_static, sr_dynamic, sr_rolling],
        "(a) Success Rate",
        "Rate (%)"
    )
    grouped_bars(
        axes[1],
        [ev_static, ev_dynamic, ev_rolling],
        "(b) Evaluation-Reference Validity",
        "Rate (%)"
    )
    grouped_bars(
        axes[2],
        [pa_static, pa_dynamic, pa_rolling],
        "(c) Protocol Adherence",
        "Rate (%)"
    )

    # annotate the key delta arrows on panel (a)
    ax = axes[0]
    ax.annotate("", xy=(x_wf[0] + width, 62), xytext=(x_wf[0], 102),
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))
    ax.text(x_wf[0] + 0.5 * width, 85, "−40pp\n(protocol\nfailures)",
            fontsize=6, color="gray", ha="center")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig5_component_ablation.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 6 — Command-following challenge breakdown
# ---------------------------------------------------------------------------

def fig6_command_challenge():
    """
    Grouped bar chart comparing B2, B3, B4 on four command-challenge metrics.
    """
    metrics = [
        "Overall\nSuccess",
        "Feasible\nCmd Success",
        "Infeasible\nDetection",
        "Unsafe\nRejection",
    ]
    # B2, B3, B4 values (%)
    b2_vals = [32.5,  10.71, 100.0, 100.0]
    b3_vals = [15.0,  20.0,    0.0,   0.0]
    b4_vals = [97.5,  96.43, 100.0, 100.0]

    x = np.arange(len(metrics))
    width = 0.25

    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    fig.suptitle(
        "Figure 6. Command-Following Challenge: B2 vs B3 vs B4",
        fontsize=9, fontweight="bold"
    )

    bars_b2 = ax.bar(x - width, b2_vals, width, label="B2 (no tools)",
                     color=C_L2, alpha=0.85)
    bars_b3 = ax.bar(x,         b3_vals, width, label="B3 (MCP, no skill)",
                     color=C_B3, alpha=0.85)
    bars_b4 = ax.bar(x + width, b4_vals, width, label="B4 (MCP + skill)",
                     color=C_B4, alpha=0.85)

    ax.set_ylim(0, 115)
    ax.set_ylabel("Rate (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.legend(loc="upper right")

    # annotate B4 bars
    for bar, val in zip(bars_b4, b4_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=7, color=C_B4,
                fontweight="bold")

    # note on B2 infeasible/unsafe: text-only, not tool-grounded
    ax.text(2.0, 105, "B2: text-only\n(not tool-grounded)", fontsize=6.5,
            color="gray", ha="center", style="italic")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig6_command_challenge.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating PyResOps paper figures...")
    fig4_tool_use_validation()
    fig5_component_ablation()
    fig6_command_challenge()
    print("All figures generated successfully.")
