"""Statistics figure: dispatch success rates and command execution rates."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from _chapter5_common import (
    STAGE3_ACCEPTED,
    WORKFLOW_TOTALS,
    bool_count,
    load_dynamic_command,
    load_stage1_dynamic,
    load_stage1_rolling,
    load_static_instruction,
    read_csv,
    savefig,
    setup_style,
)


def _stage1_workflow_rates():
    static = read_csv("experiments/results/stage1/static/all_events_metrics.csv")
    dynamic = load_stage1_dynamic()
    rolling = load_stage1_rolling()
    datasets = [("Static", static), ("Dynamic", dynamic), ("Rolling", rolling)]
    totals = [len(df) for _, df in datasets]
    accepted = [bool_count(df["accepted"]) for _, df in datasets]
    safe = [len(df) - bool_count(df["hard_violation"]) for _, df in datasets]
    return datasets, totals, accepted, safe


def _static_instruction_rates():
    df = load_static_instruction()
    total = len(df)
    return {
        "Family command": bool_count(df["command_compliance"]) / total * 100.0,
        "Interval setting": bool_count(df["interval_compliance"]) / total * 100.0,
        "Accepted": bool_count(df["accepted"]) / total * 100.0,
    }, total


def _dynamic_command_rates():
    df = load_dynamic_command()
    total = len(df)
    return {
        "Handling success": bool_count(df["command_handling_success"]) / total * 100.0,
        "Feasible execution": bool_count(df["feasible_execution_success"]) / total * 100.0,
        "Accepted": bool_count(df["accepted"]) / total * 100.0,
    }, total


def _plot_rate_bars(ax, labels, rates, counts, title, color) -> None:
    x = np.arange(len(labels))
    bars = ax.bar(x, rates, color=color, alpha=0.86, width=0.55)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Rate (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title)
    for bar, rate, count in zip(bars, rates, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(rate + 1.4, 104),
            count,
            ha="center",
            va="bottom",
            fontsize=8,
        )


def generate() -> None:
    setup_style()
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.4))

    datasets, totals, accepted, safe = _stage1_workflow_rates()
    workflow_labels = [name for name, _ in datasets]
    x = np.arange(len(workflow_labels))
    width = 0.34
    accepted_rates = [a / t * 100.0 for a, t in zip(accepted, totals)]
    safe_rates = [s / t * 100.0 for s, t in zip(safe, totals)]
    ax = axes[0, 0]
    ax.bar(x - width / 2, accepted_rates, width, color="#1a9850", alpha=0.86, label="Accepted")
    ax.bar(x + width / 2, safe_rates, width, color="#4575b4", alpha=0.86, label="Hard-safe")
    ax.set_ylim(0, 108)
    ax.set_ylabel("Rate (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(workflow_labels)
    ax.set_title("(a) Deterministic dispatch success")
    ax.legend(frameon=False, loc="lower right")
    for xi, a, t in zip(x, accepted, totals):
        ax.text(xi - width / 2, 101, f"{a}/{t}", ha="center", fontsize=7, rotation=90)

    static_rates, static_total = _static_instruction_rates()
    _plot_rate_bars(
        axes[0, 1],
        list(static_rates.keys()),
        list(static_rates.values()),
        [f"{static_total}/{static_total}"] * len(static_rates),
        "(b) Static instruction execution",
        "#1a9850",
    )

    dynamic_rates, dynamic_total = _dynamic_command_rates()
    _plot_rate_bars(
        axes[1, 0],
        list(dynamic_rates.keys()),
        list(dynamic_rates.values()),
        [f"{dynamic_total}/{dynamic_total}"] * len(dynamic_rates),
        "(c) Dynamic command execution",
        "#984ea3",
    )

    workflows = ["static", "dynamic", "rolling", "total"]
    ax = axes[1, 1]
    width = 0.23
    colors = ["#4575b4", "#1a9850", "#984ea3"]
    for i, (name, vals) in enumerate(STAGE3_ACCEPTED.items()):
        accepted_counts = [vals.get(w, sum(vals.values())) for w in workflows]
        total_counts = [WORKFLOW_TOTALS.get(w, 462) for w in workflows]
        rates = [a / t * 100.0 for a, t in zip(accepted_counts, total_counts)]
        ax.bar(np.arange(len(workflows)) + (i - 1) * width, rates, width, label=name, color=colors[i], alpha=0.86)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Rate (%)")
    ax.set_xticks(np.arange(len(workflows)))
    ax.set_xticklabels(["Static", "Dynamic", "Rolling", "Total"])
    ax.set_title("(d) LLM/MCP fail-closed acceptance")
    ax.legend(frameon=False, loc="lower right", fontsize=7)

    fig.suptitle("Dispatch success and command execution rates", y=0.995, fontsize=10, weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    savefig(fig, "fig5_4_dispatch_success_rates", category="statistics")


if __name__ == "__main__":
    generate()

