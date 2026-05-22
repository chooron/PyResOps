"""Generate Figure 6: final execution outcomes summary."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Rectangle

OUT_DIR = Path(__file__).resolve().parent

COLORS = {
    "white": "#FFFFFF",
    "text": "#222222",
    "muted": "#666666",
    "grid": "#D9D9D9",
    "spine": "#BFBFBF",
    "green": "#4CAF50",
    "green_dark": "#1F6F2B",
    "green_light": "#DFF3DF",
    "blue": "#2F78D2",
    "blue_light": "#D9E8F5",
    "orange": "#F28E1C",
    "orange_light": "#FFE3B8",
    "gray": "#BFBFBF",
    "gray_dark": "#777777",
    "gray_light": "#F4F4F4",
}

SCENARIOS = [
    "Main workflow set",
    "Static subset",
    "Dynamic retain/replan",
    "Command intervention",
    "Rolling operation",
    "Forecast-error audit",
]
SCENARIO_KEYS = [f"S{i}" for i in range(1, len(SCENARIOS) + 1)]
SCENARIO_FOOTNOTE = (
    "Scenarios: S1 Main workflow set; S2 Static subset; S3 Dynamic retain/replan; "
    "S4 Command intervention; S5 Rolling operation; S6 Forecast-error audit."
)
MODELS = ["MiMo v2.5", "MiniMax M2.5", "Claude Haiku 4.5"]
ACCEPTED = {
    "Main workflow set": [457, 451, 452],
    "Static subset": [93, 87, 94],
    "Dynamic retain/replan": [48, 43, 41],
    "Command intervention": [38, 39, 40],
    "Rolling operation": [368, 367, 370],
    "Forecast-error audit": [51, 51, 51],
}
TOTALS = {
    "Main workflow set": [462, 462, 462],
    "Static subset": [96, 96, 96],
    "Dynamic retain/replan": [48, 48, 48],
    "Command intervention": [40, 40, 40],
    "Rolling operation": [373, 373, 373],
    "Forecast-error audit": [51, 51, 51],
}
RATES = {
    "Main workflow set": [98.9, 97.6, 97.8],
    "Static subset": [96.9, 90.6, 97.9],
    "Dynamic retain/replan": [100.0, 89.6, 85.4],
    "Command intervention": [95.0, 97.5, 100.0],
    "Rolling operation": [98.7, 98.4, 99.2],
    "Forecast-error audit": [100.0, 100.0, 100.0],
}
SCENARIO_MEAN = {
    "Main workflow set": 98.1,
    "Static subset": 95.1,
    "Dynamic retain/replan": 91.7,
    "Command intervention": 97.5,
    "Rolling operation": 98.8,
    "Forecast-error audit": 100.0,
}
OVERALL_MODEL_ACCEPTANCE = {
    "MiMo v2.5": {"rate": 98.9, "count": "1,055/1,070"},
    "MiniMax M2.5": {"rate": 97.6, "count": "1,038/1,070"},
    "Claude Haiku 4.5": {"rate": 97.8, "count": "1,048/1,070"},
}
OVERALL_MEAN = 98.1
ROLLING_TOTAL = 373
LLM_CALLED_REPLANS = 142
DETERMINISTIC_RETAIN_AUDIT_ROWS = 231
LLM_CALLED_PCT = 38.1
RETAIN_PCT = 61.9
LLM_CALL_REDUCTION = 61.9
ABLATION_LABELS = ["Text-only", "Tools-only", "Tools + workflow skills"]
ABLATION_RATES = [0.0, 87.5, 100.0]
ABLATION_COUNTS = ["0/40", "35/40", "40/40"]
FAILURE_MODELS = ["MiMo v2.5", "MiniMax M2.5", "Claude Haiku 4.5"]
WRONG_TOOL_ORDER = [0, 4, 7]
MISSING_REQUIRED_TOOL = [0, 3, 3]
MISSING_EVALUATION_REFERENCE = [5, 4, 0]
CALLOUT_1 = "0 hard-constraint violations"
CALLOUT_2 = "0 downstream-release violations"


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.serif": ["Times New Roman"],
            "font.size": 10.5,
            "axes.titlesize": 11.4,
            "axes.labelsize": 11.0,
            "xtick.labelsize": 10.0,
            "ytick.labelsize": 10.0,
            "legend.fontsize": 9.8,
            "axes.edgecolor": COLORS["spine"],
            "axes.labelcolor": COLORS["text"],
            "xtick.color": COLORS["text"],
            "ytick.color": COLORS["text"],
            "text.color": COLORS["text"],
            "figure.facecolor": COLORS["white"],
            "savefig.facecolor": COLORS["white"],
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def simplify_axes(ax, *, grid_axis=None) -> None:
    ax.set_facecolor(COLORS["white"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["spine"])
    ax.spines["bottom"].set_color(COLORS["spine"])
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)
    if grid_axis:
        ax.grid(axis=grid_axis, color=COLORS["grid"], linewidth=0.55, alpha=0.75)
        ax.set_axisbelow(True)


def add_panel_label(ax, label: str) -> None:
    ax.text(
        0.0,
        1.035,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=13,
        fontweight="bold",
        color=COLORS["text"],
    )


def contrast_text_color(face) -> str:
    r, g, b, _ = face
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return COLORS["text"] if luminance > 0.58 else COLORS["white"]


def panel_a(ax) -> None:
    add_panel_label(ax, "(a)")
    ax.set_axis_off()
    cmap = LinearSegmentedColormap.from_list(
        "acceptance_green", ["#F5FAF3", "#DFF3DF", "#8FD18E", COLORS["green"]]
    )
    norm = Normalize(vmin=84.0, vmax=100.0)
    col_labels = MODELS + ["Mean"]
    n_rows = len(SCENARIOS)
    n_cols = len(col_labels)
    ax.set_xlim(0.0, n_cols)
    ax.set_ylim(n_rows + 1.12, -0.66)

    for j, label in enumerate(col_labels):
        ax.text(j + 0.5, -0.28, label, ha="center", va="center", fontsize=10.5, fontweight="bold")

    for i, (scenario, display_label) in enumerate(zip(SCENARIOS, SCENARIO_KEYS)):
        ax.text(
            -0.08,
            i + 0.5,
            display_label,
            ha="right",
            va="center",
            fontsize=11.3,
            fontweight="bold",
            clip_on=False,
        )
        row_rates = RATES[scenario] + [SCENARIO_MEAN[scenario]]
        for j, value in enumerate(row_rates):
            face = cmap(norm(value))
            if j == 3:
                face = cmap(norm(value * 0.65 + 35.0))
            ax.add_patch(
                Rectangle(
                    (j, i),
                    1.0,
                    1.0,
                    facecolor=face,
                    edgecolor=COLORS["white"],
                    linewidth=1.2,
                )
            )
            text = (
                f"{ACCEPTED[scenario][j]}/{TOTALS[scenario][j]}\n{value:.1f}%"
                if j < 3
                else f"{value:.1f}%"
            )
            ax.text(
                j + 0.5,
                i + 0.5,
                text,
                ha="center",
                va="center",
                fontsize=10.0,
                fontweight="bold",
                color=contrast_text_color(face),
            )

    for j in range(n_cols):
        ax.add_patch(
            Rectangle(
                (j, n_rows + 0.10),
                1.0,
                1.0,
                facecolor=COLORS["gray_light"],
                edgecolor=COLORS["white"],
                linewidth=1.2,
            )
        )
    ax.text(
        -0.08,
        n_rows + 0.60,
        "Mean",
        ha="right",
        va="center",
        fontsize=11.0,
        fontweight="bold",
        color=COLORS["text"],
        clip_on=False,
    )
    for j, model in enumerate(MODELS):
        item = OVERALL_MODEL_ACCEPTANCE[model]
        ax.text(j + 0.5, n_rows + 0.49, f"{item['rate']:.1f}%", ha="center", va="center", fontsize=10.1, fontweight="bold")
        ax.text(j + 0.5, n_rows + 0.80, f"({item['count']})", ha="center", va="center", fontsize=9.1, color=COLORS["muted"])
    ax.text(3.5, n_rows + 0.60, f"{OVERALL_MEAN:.1f}%", ha="center", va="center", fontsize=10.3, fontweight="bold", color=COLORS["text"])
    ax.add_patch(Rectangle((0, 0), n_cols, n_rows, facecolor="none", edgecolor=COLORS["spine"], linewidth=0.8))
    ax.add_patch(Rectangle((0, n_rows + 0.10), n_cols, 1.0, facecolor="none", edgecolor=COLORS["spine"], linewidth=0.8))


def panel_b(ax) -> None:
    add_panel_label(ax, "(b)")
    simplify_axes(ax, grid_axis="x")
    y = np.arange(len(SCENARIOS))
    height = 0.22
    model_colors = [COLORS["green"], COLORS["blue"], COLORS["orange"]]
    offsets = [-height, 0.0, height]
    for idx, (model, color, offset) in enumerate(zip(MODELS, model_colors, offsets)):
        values = [RATES[scenario][idx] for scenario in SCENARIOS]
        bars = ax.barh(y + offset, values, height=height, color=color, edgecolor=COLORS["white"], linewidth=0.8, label=model)
        for bar, value in zip(bars, values):
            ax.text(value + 0.25, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center", ha="left", fontsize=9.5)

    ax.set_yticks(y, SCENARIO_KEYS)
    ax.invert_yaxis()
    ax.set_xlim(80, 102)
    ax.set_xlabel("Acceptance rate (%)", labelpad=6)
    ax.tick_params(axis="y", labelsize=10.8, pad=4)
    for label in ax.get_yticklabels():
        label.set_fontweight("bold")
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 0.99),
        ncol=3,
        frameon=False,
        fontsize=9.8,
        handlelength=1.3,
        columnspacing=1.2,
    )


def panel_c(ax) -> None:
    add_panel_label(ax, "(c)")
    simplify_axes(ax, grid_axis="y")
    ax.set_ylim(0, 400)
    ax.set_xlim(-0.7, 0.7)
    ax.set_ylabel("Rolling checks")
    ax.set_xticks([])
    ax.text(0.5, 0.91, f"{LLM_CALL_REDUCTION:.1f}% LLM-call reduction", transform=ax.transAxes, ha="center", va="center", fontsize=11.6, fontweight="bold", color=COLORS["blue"])
    ax.text(0.5, 0.835, "Full audit coverage retained.", transform=ax.transAxes, ha="center", va="center", fontsize=9.6, color=COLORS["muted"])
    ax.text(0.5, 0.765, f"{ROLLING_TOTAL} rolling checks", transform=ax.transAxes, ha="center", va="center", fontsize=10.1, fontweight="bold")
    bar_width = 0.42
    ax.bar([0], [LLM_CALLED_REPLANS], width=bar_width, color=COLORS["blue"], edgecolor=COLORS["spine"], linewidth=0.8, label="LLM-called replans")
    ax.bar([0], [DETERMINISTIC_RETAIN_AUDIT_ROWS], bottom=[LLM_CALLED_REPLANS], width=bar_width, color=COLORS["blue_light"], edgecolor=COLORS["spine"], linewidth=0.8, label="Deterministic retain audit rows")
    ax.text(0, LLM_CALLED_REPLANS / 2, f"{LLM_CALLED_REPLANS}\n({LLM_CALLED_PCT:.1f}%)", ha="center", va="center", fontsize=9.8, fontweight="bold", color=COLORS["white"])
    ax.text(0, LLM_CALLED_REPLANS + DETERMINISTIC_RETAIN_AUDIT_ROWS / 2, f"{DETERMINISTIC_RETAIN_AUDIT_ROWS}\n({RETAIN_PCT:.1f}%)", ha="center", va="center", fontsize=9.8, fontweight="bold", color=COLORS["text"])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.24), frameon=False, fontsize=9.4, ncol=1)


def panel_d_top(ax) -> None:
    simplify_axes(ax, grid_axis="y")
    ax.text(-0.04, 1.12, "(d)", transform=ax.transAxes, ha="left", va="bottom", fontsize=13, fontweight="bold", color=COLORS["text"])
    ax.text(
        0.02,
        0.96,
        "Ablation run by MiMo v2.5",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10.2,
        fontweight="bold",
        color=COLORS["green_dark"],
        bbox=dict(boxstyle="round,pad=0.20", facecolor=COLORS["white"], edgecolor="none", alpha=0.88),
    )
    x = np.arange(len(ABLATION_LABELS)) * 1.22
    bars = ax.bar(x, ABLATION_RATES, color=COLORS["green"], edgecolor=COLORS["spine"], linewidth=0.8, width=0.58)
    ax.set_xticks(x, ["Text-only", "Tools-only", "Tools + workflow\nskills"])
    ax.set_ylabel("Ablation\nacceptance (%)", labelpad=8)
    ax.set_xlim(x[0] - 0.50, x[-1] + 0.50)
    ax.set_ylim(0, 110)
    ax.set_yticks([0, 50, 100])
    for bar, count, rate in zip(bars, ABLATION_COUNTS, ABLATION_RATES):
        ax.text(bar.get_x() + bar.get_width() / 2, max(rate + 3.5, 7.0), f"{count}\n{rate:.1f}%", ha="center", va="bottom", fontsize=9.8, fontweight="bold")


def panel_d_bottom(ax) -> None:
    simplify_axes(ax, grid_axis="y")
    x = np.arange(len(FAILURE_MODELS))
    width = 0.22
    series = [
        (WRONG_TOOL_ORDER, COLORS["orange"], "Wrong tool order", -width),
        (MISSING_REQUIRED_TOOL, COLORS["green"], "Missing required tool", 0.0),
        (MISSING_EVALUATION_REFERENCE, COLORS["blue"], "Missing evaluation reference", width),
    ]
    for values, color, label, offset in series:
        bars = ax.bar(x + offset, values, width=width, color=color, edgecolor=COLORS["white"], linewidth=0.6, label=label)
        for bar, value in zip(bars, values):
            if value >= 7:
                y_pos = value - 0.35
                va = "top"
                text_color = COLORS["white"]
            else:
                y_pos = value + 0.18
                va = "bottom"
                text_color = COLORS["text"]
            ax.text(bar.get_x() + bar.get_width() / 2, y_pos, f"{value}", ha="center", va=va, fontsize=9.8, fontweight="bold", color=text_color)
    ax.set_xticks(x, FAILURE_MODELS)
    ax.set_ylabel("Protocol-level failures\n(rejected records)")
    ax.set_ylim(0, 10.0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.04), ncol=3, frameon=False, fontsize=9.6)
    for xc, text in [(0.22, CALLOUT_1), (0.62, CALLOUT_2)]:
        ax.text(
            xc,
            -0.36,
            text,
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=9.0,
            fontweight="bold",
            color=COLORS["text"],
            bbox=dict(boxstyle="round,pad=0.28", facecolor=COLORS["white"], edgecolor=COLORS["spine"], linewidth=0.9),
            clip_on=False,
        )


def main() -> None:
    setup_style()

    fig = plt.figure(figsize=(14.2, 7.45), facecolor=COLORS["white"])
    outer = fig.add_gridspec(2, 1, height_ratios=[1.12, 1.03], hspace=0.30)
    top = outer[0].subgridspec(1, 2, width_ratios=[0.52, 0.48], wspace=0.09)
    bottom = outer[1].subgridspec(1, 2, width_ratios=[0.34, 0.66], wspace=0.16)

    ax_a = fig.add_subplot(top[0, 0])
    ax_b = fig.add_subplot(top[0, 1])
    ax_c = fig.add_subplot(bottom[0, 0])

    d_grid = bottom[0, 1].subgridspec(2, 1, height_ratios=[0.92, 1.08], hspace=0.50)
    ax_d_top = fig.add_subplot(d_grid[0, 0])
    ax_d_bottom = fig.add_subplot(d_grid[1, 0])

    panel_a(ax_a)
    panel_b(ax_b)
    panel_c(ax_c)
    panel_d_top(ax_d_top)
    panel_d_bottom(ax_d_bottom)

    fig.text(
        0.5,
        0.015,
        SCENARIO_FOOTNOTE,
        ha="center",
        va="top",
        fontsize=10.0,
        color=COLORS["text"],
    )

    fig.savefig(OUT_DIR / "final_execution_outcomes_refined.png", dpi=300, bbox_inches="tight", pad_inches=0.08)
    fig.savefig(OUT_DIR / "final_execution_outcomes_refined.pdf", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print("Saved PNG and PDF.")


if __name__ == "__main__":
    main()
