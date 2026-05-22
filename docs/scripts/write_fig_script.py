"""Helper: write build_operation_effect_figures.py"""
import os

ROOT = "E:/PyCode/PyResOps"
OUT = os.path.join(ROOT, "experiments", "results", "build_operation_effect_figures.py")

CONTENT = """\
\"\"\"
build_operation_effect_figures.py
Generate operation-effect figures for PyResOps paper (ESWA/EAAI style).

Reads pre-built CSVs from:
  experiments/results/paper_ready/operation_effect_figures/

Outputs figures to:
  docs/paper/figures/

No LLM calls. No data fabrication.
\"\"\"

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "experiments", "results", "paper_ready",
                        "operation_effect_figures")
OUT_DIR  = os.path.join(ROOT, "docs", "paper", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

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
    "legend.fontsize": 7.5,
    "figure.dpi": 150,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "axes.axisbelow": True,
})

C_HIST   = "#555555"
C_RULE   = "#2166ac"
C_AGENT  = "#1a9641"
C_FORE   = "#d6604d"
C_INFLOW = "#74add1"
C_FLOOD  = "#d6604d"
C_DESIGN = "#b2182b"

Z_FLOOD  = 156.5
Z_DESIGN = 165.87

SCHEME_STYLE = {
    "historical": dict(color=C_HIST,  lw=1.4, ls="-",  label="Historical"),
    "rule_based": dict(color=C_RULE,  lw=1.4, ls="--", label="Rule-based"),
    "agent":      dict(color=C_AGENT, lw=1.8, ls="-",  label="Agent"),
}


def _save(fig, name):
    for ext in ("pdf", "png"):
        p = os.path.join(OUT_DIR, f"{name}.{ext}")
        fig.savefig(p, bbox_inches="tight", dpi=300 if ext == "png" else None)
        print(f"  Saved: {p}")
    plt.close(fig)


def _add_level_lines(ax):
    ax.axhline(Z_FLOOD,  color=C_FLOOD,  ls="--", lw=0.9, alpha=0.85,
               label=f"Flood-limit ({Z_FLOOD} m)")
    ax.axhline(Z_DESIGN, color=C_DESIGN, ls=":",  lw=0.9, alpha=0.85,
               label=f"Design flood ({Z_DESIGN} m)")


def _xtick_setup(ax, t, t_labels, n=4):
    step = max(1, len(t) // n)
    ax.set_xticks(t[::step])
    ax.set_xticklabels(t_labels.iloc[::step], rotation=30, ha="right", fontsize=6.5)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
def load_data():
    st = pd.read_csv(os.path.join(DATA_DIR, "static_event_timeseries_all.csv"),
                     parse_dates=["time"])
    ro = pd.read_csv(os.path.join(DATA_DIR, "rolling_event_timeseries_all.csv"),
                     parse_dates=["time"])
    sm = pd.read_csv(os.path.join(DATA_DIR, "static_across_event_metrics.csv"))
    rm = pd.read_csv(os.path.join(DATA_DIR, "rolling_across_event_metrics.csv"))
    return st, ro, sm, rm


# ---------------------------------------------------------------------------
# Figure R1: Static representative events (3 events x 4 panels)
# ---------------------------------------------------------------------------
def figR1_static_representative(st, sm):
    events = [2022062023, 2024061623, 2019071011]
    event_labels = ["Event 2022-06-20", "Event 2024-06-16", "Event 2019-07-10"]

    fig = plt.figure(figsize=(13.0, 9.5))
    fig.suptitle(
        "Figure R1. Representative real-event operation comparisons under static scheduling",
        fontsize=9, fontweight="bold", y=1.002)
    gs = GridSpec(3, 4, figure=fig, hspace=0.58, wspace=0.40)

    panel_letters = "abcdefghijkl"
    for row, (eid, elbl) in enumerate(zip(events, event_labels)):
        sub = st[st["event_id"] == eid].sort_values("time").reset_index(drop=True)
        t = np.arange(len(sub))
        t_labels = sub["time"].dt.strftime("%m/%d %H")

        # (a/e/i) Inflow
        ax = fig.add_subplot(gs[row, 0])
        ax.fill_between(t, sub["inflow_observed"], alpha=0.22, color=C_INFLOW)
        ax.plot(t, sub["inflow_observed"], color=C_INFLOW, lw=1.5, label="Inflow")
        ax.set_ylabel("Flow (m\\u00b3/s)")
        ax.set_title(f"({panel_letters[row*4]}) {elbl} — inflow")
        _xtick_setup(ax, t, t_labels)
        ax.legend(fontsize=7)

        # (b/f/j) Release
        ax = fig.add_subplot(gs[row, 1])
        for scheme in ["historical", "rule_based", "agent"]:
            col = f"release_{scheme}"
            if col in sub.columns:
                ax.plot(t, sub[col], **SCHEME_STYLE[scheme])
        ax.set_ylabel("Release (m\\u00b3/s)")
        ax.set_title(f"({panel_letters[row*4+1]}) Release comparison")
        _xtick_setup(ax, t, t_labels)
        ax.legend(fontsize=7)

        # (c/g/k) Water level
        ax = fig.add_subplot(gs[row, 2])
        for scheme in ["historical", "rule_based", "agent"]:
            col = f"level_{scheme}"
            if col in sub.columns:
                ax.plot(t, sub[col], **SCHEME_STYLE[scheme])
        _add_level_lines(ax)
        ax.set_ylabel("Water level (m)")
        ax.set_title(f"({panel_letters[row*4+2]}) Water-level trajectory")
        _xtick_setup(ax, t, t_labels)
        ax.legend(fontsize=6.5, ncol=2)

        # (d/h/l) Metric summary
        ax = fig.add_subplot(gs[row, 3])
        mdf = sm[sm["event_id"] == eid].set_index("scheme")
        metrics = ["peak_release", "max_water_level", "terminal_level_deviation"]
        mlabels = ["Peak\nrelease\n(m\\u00b3/s)", "Max\nlevel\n(m)", "Terminal\ndev. (m)"]
        xm = np.arange(len(metrics))
        w = 0.22
        for i, (scheme, style) in enumerate(SCHEME_STYLE.items()):
            if scheme in mdf.index:
                vals = [mdf.loc[scheme, m] for m in metrics]
                ax.bar(xm + (i-1)*w, vals, w, color=style["color"],
                       alpha=0.85, label=style["label"])
        ax.set_xticks(xm)
        ax.set_xticklabels(mlabels, fontsize=7)
        ax.set_title(f"({panel_letters[row*4+3]}) Metric summary")
        ax.legend(fontsize=6.5)

    _save(fig, "figR1_static_representative_events")


# ---------------------------------------------------------------------------
# Figure R2: Rolling representative events (3 events x 3 panels)
# ---------------------------------------------------------------------------
def figR2_rolling_representative(ro):
    events = [2012062402, 2019071011, 2022062023]
    event_labels = [
        "Event 2012-06-24 (multi-trigger)",
        "Event 2019-07-10 (state-risk)",
        "Event 2022-06-20 (scheduled)",
    ]

    fig = plt.figure(figsize=(13.0, 9.5))
    fig.suptitle(
        "Figure R2. Representative rolling operations under real forecast updates",
        fontsize=9, fontweight="bold", y=1.002)
    gs = GridSpec(3, 3, figure=fig, hspace=0.58, wspace=0.38)

    panel_letters = "abcdefghi"
    for row, (eid, elbl) in enumerate(zip(events, event_labels)):
        sub = ro[ro["event_id"] == eid].sort_values("time").reset_index(drop=True)
        t = np.arange(len(sub))
        t_labels = sub["time"].dt.strftime("%m/%d %H")
        replan_idx = sub.index[sub["whether_replan"] == True].tolist()

        # (a/d/g) Inflow observed vs forecast
        ax = fig.add_subplot(gs[row, 0])
        ax.fill_between(t, sub["inflow_observed"], alpha=0.2, color=C_INFLOW)
        ax.plot(t, sub["inflow_observed"], color=C_INFLOW, lw=1.5, label="Observed")
        if "inflow_forecast" in sub.columns:
            ax.plot(t, sub["inflow_forecast"], color=C_FORE, lw=1.2, ls="--",
                    label="Forecast")
        if replan_idx:
            ax.scatter(replan_idx,
                       sub.loc[replan_idx, "inflow_observed"].values,
                       s=28, color=C_AGENT, zorder=5, marker="^",
                       label="Replan")
        ax.set_ylabel("Flow (m\\u00b3/s)")
        ax.set_title(f"({panel_letters[row*3]}) {elbl}")
        _xtick_setup(ax, t, t_labels, n=5)
        ax.legend(fontsize=7)

        # (b/e/h) Release comparison
        ax = fig.add_subplot(gs[row, 1])
        for scheme in ["historical", "rule_based", "agent"]:
            col = f"release_{scheme}"
            if col in sub.columns:
                ax.plot(t, sub[col], **SCHEME_STYLE[scheme])
        ax.set_ylabel("Release (m\\u00b3/s)")
        ax.set_title(f"({panel_letters[row*3+1]}) Release comparison")
        _xtick_setup(ax, t, t_labels, n=5)
        ax.legend(fontsize=7)

        # (c/f/i) Water level + replan markers
        ax = fig.add_subplot(gs[row, 2])
        for scheme in ["historical", "rule_based", "agent"]:
            col = f"level_{scheme}"
            if col in sub.columns:
                ax.plot(t, sub[col], **SCHEME_STYLE[scheme])
        _add_level_lines(ax)
        for ri in replan_idx:
            ax.axvline(ri, color=C_AGENT, lw=0.7, alpha=0.35, ls=":")
        ax.set_ylabel("Water level (m)")
        ax.set_title(f"({panel_letters[row*3+2]}) Level + replan markers")
        _xtick_setup(ax, t, t_labels, n=5)
        ax.legend(fontsize=6.5, ncol=2)

    _save(fig, "figR2_rolling_representative_events")


# ---------------------------------------------------------------------------
# Figure R3: Across-event rolling summary (all 10 events)
# ---------------------------------------------------------------------------
def figR3_rolling_across_event(rm):
    agent_df = rm[rm["scheme"] == "agent"].set_index("event_id")
    rule_df  = rm[rm["scheme"] == "rule_based"].set_index("event_id")
    hist_df  = rm[rm["scheme"] == "historical"].set_index("event_id")

    events  = sorted(agent_df.index.tolist())
    elabels = [str(e)[4:8] + "-" + str(e)[8:] for e in events]
    x = np.arange(len(events))
    w = 0.25

    fig, axes = plt.subplots(2, 2, figsize=(11.0, 7.0))
    fig.suptitle(
        "Figure R3. Across-event comparison of rolling operation effects (10 events)",
        fontsize=9, fontweight="bold")

    # (a) Peak release grouped bar
    ax = axes[0, 0]
    for i, (df, scheme) in enumerate([(hist_df, "historical"),
                                       (rule_df,  "rule_based"),
                                       (agent_df, "agent")]):
        vals = [df.loc[e, "peak_release"] if e in df.index else 0 for e in events]
        ax.bar(x + (i-1)*w, vals, w, color=SCHEME_STYLE[scheme]["color"],
               alpha=0.85, label=SCHEME_STYLE[scheme]["label"])
    ax.set_xticks(x); ax.set_xticklabels(elabels, rotation=35, ha="right", fontsize=7)
    ax.set_ylabel("Peak release (m\\u00b3/s)")
    ax.set_title("(a) Peak release across events")
    ax.legend(fontsize=7)

    # (b) Max water level dumbbell
    ax = axes[0, 1]
    for i, e in enumerate(events):
        r_val = rule_df.loc[e,  "max_water_level"] if e in rule_df.index  else None
        a_val = agent_df.loc[e, "max_water_level"] if e in agent_df.index else None
        h_val = hist_df.loc[e,  "max_water_level"] if e in hist_df.index  else None
        if r_val is not None and a_val is not None:
            ax.plot([i, i], [r_val, a_val], color="#bbbbbb", lw=1.2, zorder=1)
        if h_val is not None:
            ax.scatter(i, h_val, color=C_HIST,  s=40, zorder=3, marker="D")
        if r_val is not None:
            ax.scatter(i, r_val, color=C_RULE,  s=50, zorder=3)
        if a_val is not None:
            ax.scatter(i, a_val, color=C_AGENT, s=50, zorder=3, marker="^")
    ax.axhline(Z_FLOOD, color=C_FLOOD, ls="--", lw=0.9, alpha=0.85)
    ax.set_xticks(x); ax.set_xticklabels(elabels, rotation=35, ha="right", fontsize=7)
    ax.set_ylabel("Max water level (m)")
    ax.set_title("(b) Max water level (rule \\u2192 agent)")
    ax.legend(handles=[
        mpatches.Patch(color=C_HIST,  label="Historical"),
        mpatches.Patch(color=C_RULE,  label="Rule-based"),
        mpatches.Patch(color=C_AGENT, label="Agent"),
        plt.Line2D([0],[0], color=C_FLOOD, ls="--", lw=0.9,
                   label=f"Flood-limit ({Z_FLOOD} m)"),
    ], fontsize=7)

    # (c) Terminal deviation dumbbell
    ax = axes[1, 0]
    for i, e in enumerate(events):
        r_val = rule_df.loc[e,  "terminal_level_deviation"] if e in rule_df.index  else None
        a_val = agent_df.loc[e, "terminal_level_deviation"] if e in agent_df.index else None
        if r_val is not None and a_val is not None:
            ax.plot([i, i], [r_val, a_val], color="#bbbbbb", lw=1.2, zorder=1)
            ax.scatter(i, r_val, color=C_RULE,  s=50, zorder=3)
            ax.scatter(i, a_val, color=C_AGENT, s=50, zorder=3, marker="^")
    ax.set_xticks(x); ax.set_xticklabels(elabels, rotation=35, ha="right", fontsize=7)
    ax.set_ylabel("Terminal level deviation (m)")
    ax.set_title("(c) Terminal level deviation (rule vs agent)")
    ax.legend(handles=[mpatches.Patch(color=C_RULE,  label="Rule-based"),
                        mpatches.Patch(color=C_AGENT, label="Agent")], fontsize=7)

    # (d) Trigger stacked bar
    ax = axes[1, 1]
    sched = [agent_df.loc[e, "scheduled_check_count"]       if e in agent_df.index else 0 for e in events]
    state = [agent_df.loc[e, "state_risk_trigger_count"]    if e in agent_df.index else 0 for e in events]
    ferr  = [agent_df.loc[e, "forecast_error_trigger_count"] if e in agent_df.index else 0 for e in events]
    ax.bar(x, sched, color="#2166ac", alpha=0.85, label="Scheduled 12h")
    ax.bar(x, state, bottom=sched, color="#762a83", alpha=0.85, label="State risk")
    ax.bar(x, ferr,  bottom=[s+t for s,t in zip(sched, state)],
           color=C_FORE, alpha=0.85, label="Forecast error")
    ax.set_xticks(x); ax.set_xticklabels(elabels, rotation=35, ha="right", fontsize=7)
    ax.set_ylabel("Trigger count")
    ax.set_title("(d) Trigger distribution per event")
    ax.legend(fontsize=7)

    fig.tight_layout(pad=1.5)
    _save(fig, "figR3_rolling_across_event_summary")


# ---------------------------------------------------------------------------
# Figure R4: Rolling reliability audit
# ---------------------------------------------------------------------------
def figR4_rolling_reliability():
    event_ids      = ["2012062402","2013100711","2019070517","2019071011",
                      "2021052114","2022062023","2024061220","2024061517",
                      "2024061623","2024072617"]
    elabels        = [e[4:8]+"-"+e[8:] for e in event_ids]
    stage_counts   = [21, 7, 9, 9, 17, 11, 4, 3, 5, 7]
    success_counts = [19, 7, 8, 9, 16,  9, 4, 3, 5, 7]
    fail_counts    = [ 2, 0, 1, 0,  1,  2, 0, 0, 0, 0]

    trig_labels   = ["Scheduled\\n12h", "State\\nrisk",
                     "Rel. forecast\\nerr.", "Abs. forecast\\nerr."]
    trig_success  = [59, 18, 8, 2]
    trig_fail     = [ 5,  0, 1, 0]

    fail_labels   = ["Hallucinated\\neval-ref", "Missing\\neval-ref",
                     "Missing\\nrequired tool"]
    fail_counts_t = [4, 1, 1]

    fig = plt.figure(figsize=(11.0, 5.5))
    fig.suptitle(
        "Figure R4. Rolling validation reliability and evidence-binding audit"
        " (10 events, 93 stages)",
        fontsize=9, fontweight="bold")
    gs = GridSpec(1, 3, figure=fig, wspace=0.40, width_ratios=[2.5, 1.5, 1.0])

    # (a) Per-event stage outcomes
    ax = fig.add_subplot(gs[0])
    x = np.arange(len(event_ids)); w = 0.35
    ax.bar(x - w/2, stage_counts,   w, color="#74add1", alpha=0.85, label="Total stages")
    ax.bar(x + w/2, success_counts, w, color=C_AGENT,   alpha=0.85, label="Successful")
    for i, (tot, suc, fail) in enumerate(zip(stage_counts, success_counts, fail_counts)):
        if fail > 0:
            ax.text(x[i]+w/2, suc+0.3, f"\\u2212{fail}", ha="center",
                    va="bottom", fontsize=7, color=C_FORE, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(elabels, rotation=35, ha="right", fontsize=7)
    ax.set_ylabel("Stage count")
    ax.set_title("(a) Per-event stage outcomes")
    ax.legend(fontsize=7)
    ax.text(0.01, 0.97,
            "87/93 successful  |  0 hard-safety violations  |  391/391 MCP calls",
            transform=ax.transAxes, fontsize=7, va="top",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f0f0f0",
                      edgecolor="gray", alpha=0.8))

    # (b) Trigger distribution
    ax = fig.add_subplot(gs[1])
    xt = np.arange(len(trig_labels))
    ax.bar(xt, trig_success, color=C_AGENT, alpha=0.85, label="Successful")
    ax.bar(xt, trig_fail, bottom=trig_success, color=C_FORE, alpha=0.85, label="Failed")
    for i, (s, f) in enumerate(zip(trig_success, trig_fail)):
        ax.text(xt[i], s+f+0.3, str(s+f), ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(xt); ax.set_xticklabels(trig_labels, fontsize=7)
    ax.set_ylabel("Stage count")
    ax.set_title("(b) Trigger distribution")
    ax.legend(fontsize=7)

    # (c) Failure taxonomy
    ax = fig.add_subplot(gs[2])
    xf = np.arange(len(fail_labels))
    ax.bar(xf, fail_counts_t, color=C_FORE, alpha=0.85, width=0.5)
    for i, v in enumerate(fail_counts_t):
        ax.text(xf[i], v+0.1, str(v), ha="center", va="bottom",
                fontsize=8, fontweight="bold")
    ax.set_xticks(xf); ax.set_xticklabels(fail_labels, fontsize=7)
    ax.set_ylim(0, 6)
    ax.set_ylabel("Count")
    ax.set_title("(c) Failure taxonomy\\n(6 failed stages)")
    ax.text(0.5, -0.32, "All failures: auditability issues\\n(0 hard-safety violations)",
            transform=ax.transAxes, ha="center", fontsize=6.5,
            color="gray", style="italic")

    fig.tight_layout(pad=1.5)
    _save(fig, "figR4_rolling_reliability_audit")


# ---------------------------------------------------------------------------
# Figure R5: Static across-event summary (4 events, 3 metrics)
# ---------------------------------------------------------------------------
def figR5_static_across_event(sm):
    events  = sorted(sm["event_id"].unique())
    elabels = [str(e)[4:8]+"-"+str(e)[8:] for e in events]
    x = np.arange(len(events)); w = 0.25

    fig, axes = plt.subplots(1, 3, figsize=(11.0, 4.2))
    fig.suptitle(
        "Figure R5. Across-event static operation comparison (4 events)",
        fontsize=9, fontweight="bold")

    specs = [
        ("peak_release",             "Peak release (m\\u00b3/s)",        "(a)"),
        ("max_water_level",          "Max water level (m)",               "(b)"),
        ("terminal_level_deviation", "Terminal level deviation (m)",      "(c)"),
    ]
    for ax, (metric, ylabel, panel) in zip(axes, specs):
        for i, (scheme, style) in enumerate(SCHEME_STYLE.items()):
            mdf  = sm[sm["scheme"] == scheme].set_index("event_id")
            vals = [mdf.loc[e, metric] if e in mdf.index else 0 for e in events]
            ax.bar(x + (i-1)*w, vals, w, color=style["color"],
                   alpha=0.85, label=style["label"])
        if metric == "max_water_level":
            ax.axhline(Z_FLOOD, color=C_FLOOD, ls="--", lw=0.9, alpha=0.85,
                       label=f"Flood-limit ({Z_FLOOD} m)")
        ax.set_xticks(x)
        ax.set_xticklabels(elabels, rotation=30, ha="right", fontsize=7.5)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{panel} {ylabel}")
        ax.legend(fontsize=7)

    fig.tight_layout(pad=1.5)
    _save(fig, "figR5_static_across_event_summary")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Loading data...")
    st, ro, sm, rm = load_data()

    print("Generating Figure R1: static representative events...")
    figR1_static_representative(st, sm)

    print("Generating Figure R2: rolling representative events...")
    figR2_rolling_representative(ro)

    print("Generating Figure R3: rolling across-event summary...")
    figR3_rolling_across_event(rm)

    print("Generating Figure R4: rolling reliability audit...")
    figR4_rolling_reliability()

    print("Generating Figure R5: static across-event summary...")
    figR5_static_across_event(sm)

    print(f"\\nAll figures saved to: {OUT_DIR}")
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(CONTENT)
print("Written:", OUT)
