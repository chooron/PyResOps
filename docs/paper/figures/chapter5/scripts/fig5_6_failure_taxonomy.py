"""Figure 5.6: fail-closed rejection taxonomy."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from _chapter5_common import FAILURES, savefig, setup_style


def generate() -> None:
    setup_style()
    names = list(FAILURES.keys())
    reasons = ["wrong_tool_order", "missing_required_tool", "missing_eval_ref"]
    labels = ["Wrong tool order", "Missing tool", "Missing eval ref"]
    colors = ["#e41a1c", "#ff7f00", "#377eb8"]
    bottoms = np.zeros(len(names))
    x = np.arange(len(names))

    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    for reason, label, color in zip(reasons, labels, colors):
        vals = [FAILURES[name][reason] for name in names]
        bars = ax.bar(x, vals, bottom=bottoms, label=label, color=color, alpha=0.86)
        for bar, bottom, val in zip(bars, bottoms, vals):
            if val:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bottom + val / 2,
                    str(val),
                    ha="center",
                    va="center",
                    color="white",
                    weight="bold",
                    fontsize=8,
                )
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Rejected records")
    ax.set_title("Failure modes under fail-closed validation")
    ax.legend(loc="upper right", frameon=False)
    ax.text(
        0.5,
        -0.22,
        "Hard-safety violations = 0 and downstream-routing violations = 0 for all executors.",
        ha="center",
        transform=ax.transAxes,
        fontsize=8,
    )
    fig.subplots_adjust(bottom=0.22)
    savefig(fig, "fig5_5_failure_taxonomy", category="statistics")


if __name__ == "__main__":
    generate()
