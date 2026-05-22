"""
Figures 1–3: Pure schematic drawings (architecture, workflow contracts, Tankeng context).
These figures use matplotlib patches and annotations only — no data files required.

Output:
  docs/paper/figures/fig01_architecture.{pdf,png}
  docs/paper/figures/fig02_workflow_contracts.{pdf,png}
  docs/paper/figures/fig03_tankeng_context.{pdf,png}
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 9,
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.spines.bottom": False,
})

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)


def _box(ax, x, y, w, h, text, facecolor, edgecolor="#333333", fontsize=8, bold=False):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.02",
                          facecolor=facecolor, edgecolor=edgecolor, linewidth=1.0)
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, fontweight="bold" if bold else "normal", wrap=True)


def _arrow(ax, x0, y0, x1, y1, color="#555555"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.2))


# ---------------------------------------------------------------------------
# Figure 1 — PyResOps architecture
# ---------------------------------------------------------------------------
def fig01_architecture():
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.suptitle("Figure 1. PyResOps architecture", fontsize=9, fontweight="bold")

    # Layer bands
    band_colors = ["#d1e5f0", "#e8f5e9", "#fff3e0"]
    band_labels = ["Layer 1: Reservoir-operation kernel",
                   "Layer 2: MCP tool interface (26 tools)",
                   "Layer 3: Validation layer"]
    for i, (col, lbl) in enumerate(zip(band_colors, band_labels)):
        y = 0.5 + i * 2.3
        rect = mpatches.FancyBboxPatch((0.3, y), 9.4, 2.0,
                                       boxstyle="round,pad=0.05",
                                       facecolor=col, edgecolor="#aaaaaa", linewidth=0.8)
        ax.add_patch(rect)
        ax.text(0.55, y + 1.85, lbl, fontsize=7.5, color="#333333", style="italic")

    # Kernel components
    kernel_items = ["Reservoir\nspecification", "Simulation\n(water balance)",
                    "Optimization\n(Powell / scalar)", "Evaluation\n(J(π))",
                    "Hard-constraint\ncheck H(π)", "Rolling-state\nmanagement"]
    for j, item in enumerate(kernel_items):
        x = 0.5 + j * 1.52
        _box(ax, x, 0.65, 1.35, 1.6, item, "#aed6f1", fontsize=7)

    # Tool interface
    tool_items = ["prepare_event", "optimize_release_plan", "simulate_release_plan",
                  "evaluate_release_plan", "check_hard_constraints",
                  "run_static/dynamic/rolling_workflow"]
    for j, item in enumerate(tool_items):
        x = 0.5 + j * 1.52
        _box(ax, x, 2.95, 1.35, 1.6, item, "#a9dfbf", fontsize=6.5)

    # Validation layer
    val_items = ["Workflow\ncontract check\n(Order)", "Eval-ref\nvalidity\n(Ref)",
                 "Hard-safety\ncheck H(π)", "Schema\nvalidation",
                 "Accept /\nReject\n(fail-closed)"]
    for j, item in enumerate(val_items):
        x = 0.5 + j * 1.82
        _box(ax, x, 5.25, 1.65, 1.6, item, "#fad7a0", fontsize=7)

    # MCP transport arrow (right side)
    ax.annotate("MCP transport\n(Agno MCPTools)", xy=(9.7, 4.0), xytext=(9.7, 6.5),
                ha="center", fontsize=7, color="#555555",
                arrowprops=dict(arrowstyle="<->", color="#555555", lw=1.2))

    # LLM agent box (top)
    _box(ax, 3.5, 7.1, 3.0, 0.7, "LLM agent (MiMo v2.5 / other executors)",
         "#f9ebea", edgecolor="#c0392b", fontsize=8, bold=True)
    _arrow(ax, 5.0, 7.1, 5.0, 6.85)

    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig01_architecture.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 2 — Workflow contracts
# ---------------------------------------------------------------------------
def fig02_workflow_contracts():
    fig, axes = plt.subplots(1, 3, figsize=(10.0, 5.0))
    fig.suptitle("Figure 2. Workflow contracts for static, dynamic, and rolling operation",
                 fontsize=9, fontweight="bold")

    titles = ["(a) Static workflow", "(b) Dynamic workflow", "(c) Rolling workflow"]
    for ax, title in zip(axes, titles):
        ax.set_xlim(0, 4)
        ax.set_ylim(0, 10)
        ax.axis("off")
        ax.set_title(title, fontsize=8.5)

    # --- Static ---
    ax = axes[0]
    steps = ["prepare_event", "optimize_release_plan", "simulate_release_plan",
             "evaluate_release_plan", "validate_decision_payload", "ACCEPT"]
    colors = ["#aed6f1"] * 4 + ["#a9dfbf", "#1a9641"]
    for i, (step, col) in enumerate(zip(steps, colors)):
        y = 8.5 - i * 1.5
        _box(ax, 0.3, y - 0.5, 3.4, 1.0, step, col, fontsize=7.5)
        if i < len(steps) - 1:
            _arrow(ax, 2.0, y - 0.5, 2.0, y - 1.4)

    # --- Dynamic ---
    ax = axes[1]
    _box(ax, 0.3, 8.5, 3.4, 0.9, "prepare_event", "#aed6f1", fontsize=7.5)
    _arrow(ax, 2.0, 8.5, 2.0, 7.6)
    _box(ax, 0.3, 6.7, 3.4, 0.9, "evaluate carry-over plan", "#fad7a0", fontsize=7.5)
    _arrow(ax, 2.0, 6.7, 2.0, 5.8)
    # Diamond
    diamond = mpatches.FancyBboxPatch((0.8, 5.0), 2.4, 0.8,
                                      boxstyle="round,pad=0.05",
                                      facecolor="#fdebd0", edgecolor="#e67e22")
    ax.add_patch(diamond)
    ax.text(2.0, 5.4, "H(π)=1 and C(π)=1?", ha="center", va="center", fontsize=7)
    # Retain branch
    ax.annotate("Retain", xy=(3.7, 5.4), xytext=(3.2, 5.4),
                ha="left", fontsize=7, color="#1a9641",
                arrowprops=dict(arrowstyle="->", color="#1a9641"))
    # Replan branch
    _arrow(ax, 2.0, 5.0, 2.0, 4.1)
    ax.text(2.1, 4.55, "Replan", fontsize=7, color="#d6604d")
    _box(ax, 0.3, 3.2, 3.4, 0.9, "optimize → simulate → evaluate", "#aed6f1", fontsize=7)
    _arrow(ax, 2.0, 3.2, 2.0, 2.3)
    _box(ax, 0.3, 1.4, 3.4, 0.9, "validate_decision_payload", "#a9dfbf", fontsize=7.5)
    _arrow(ax, 2.0, 1.4, 2.0, 0.5)
    _box(ax, 0.3, -0.1, 3.4, 0.7, "ACCEPT", "#1a9641", fontsize=7.5, bold=True)

    # --- Rolling ---
    ax = axes[2]
    _box(ax, 0.3, 8.5, 3.4, 0.9, "Observe state / inflow", "#aed6f1", fontsize=7.5)
    _arrow(ax, 2.0, 8.5, 2.0, 7.6)
    # Trigger box
    trig = FancyBboxPatch((0.3, 6.7), 3.4, 0.9,
                          boxstyle="round,pad=0.05",
                          facecolor="#fdebd0", edgecolor="#e67e22")
    ax.add_patch(trig)
    ax.text(2.0, 7.15, "Trigger condition?", ha="center", va="center", fontsize=7)
    ax.text(0.1, 6.5,
            "• Relative forecast error > 0.2\n• Absolute error > 150 m³/s\n• Manual trigger\n• Safety trigger",
            fontsize=6, color="#555555", va="top")
    _arrow(ax, 2.0, 6.7, 2.0, 5.8)
    ax.text(2.1, 6.25, "Trigger fires", fontsize=7, color="#d6604d")
    _box(ax, 0.3, 4.9, 3.4, 0.9, "optimize → simulate → evaluate", "#aed6f1", fontsize=7)
    _arrow(ax, 2.0, 4.9, 2.0, 4.0)
    _box(ax, 0.3, 3.1, 3.4, 0.9, "validate_decision_payload", "#a9dfbf", fontsize=7.5)
    _arrow(ax, 2.0, 3.1, 2.0, 2.2)
    _box(ax, 0.3, 1.3, 3.4, 0.9, "ACCEPT / advance horizon", "#1a9641", fontsize=7, bold=True)

    fig.tight_layout(pad=1.5)
    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig02_workflow_contracts.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 3 — Tankeng context
# ---------------------------------------------------------------------------
def fig03_tankeng_context():
    fig, ax = plt.subplots(figsize=(9.0, 4.0))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6)
    ax.axis("off")
    fig.suptitle("Figure 3. Tankeng Reservoir operation context and the PyResOps layer",
                 fontsize=9, fontweight="bold")

    # Three panels
    panel_data = [
        (0.2, 1.0, 3.2, 4.0, "#d1e5f0", "Reservoir and\nhydrological inputs",
         ["Inflow time series", "Water level / storage", "Release-capacity curves",
          "Downstream safety limits", "Forecast inflow"]),
        (4.2, 1.0, 3.2, 4.0, "#e8f5e9", "Existing engineering\ndecision-support system",
         ["Event records", "Characteristic curves", "Operating rules",
          "Human review procedure", "Reporting / approval"]),
        (8.2, 1.0, 3.6, 4.0, "#fff3e0", "PyResOps layer",
         ["Deterministic simulation", "Optimization", "Hard-constraint check",
          "MCP tool interface", "Workflow contracts", "Structured payload validation"]),
    ]

    for x, y, w, h, col, title, items in panel_data:
        rect = FancyBboxPatch((x, y), w, h,
                              boxstyle="round,pad=0.05",
                              facecolor=col, edgecolor="#888888", linewidth=1.0)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h - 0.25, title, ha="center", va="top",
                fontsize=8.5, fontweight="bold")
        for k, item in enumerate(items):
            ax.text(x + 0.15, y + h - 0.65 - k * 0.58, f"• {item}",
                    fontsize=7, va="top", color="#333333")

    # Arrows between panels
    _arrow(ax, 3.4, 3.0, 4.2, 3.0)
    _arrow(ax, 7.4, 3.0, 8.2, 3.0)

    # Note at bottom
    ax.text(6.0, 0.4,
            "PyResOps extends the existing engineering context with a verifiable model-facing workflow; it does not replace the original system.",
            ha="center", fontsize=7, color="gray", style="italic")

    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"fig03_tankeng_context.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"Saved: {path}")
    plt.close(fig)


if __name__ == "__main__":
    print("Generating schematic figures (1–3)...")
    fig01_architecture()
    fig02_workflow_contracts()
    fig03_tankeng_context()
    print("Done.")
