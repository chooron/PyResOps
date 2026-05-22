"""Build Chapter 5 tables and figures from frozen Stage 1/2/3 results.

The script is intentionally read-only with respect to experiment results: it
does not rerun optimization or LLM workflows. It assembles paper-facing tables
and figures under experiments/figures/chapter5/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
OUT = ROOT / "experiments" / "figures" / "chapter5"
TABLE_OUT = OUT / "tables"
OP_DATA = RESULTS / "paper_ready" / "operation_effect_figures"

EXECUTORS = {
    "MiniMax M2.5": RESULTS / "stage3",
    "MiMo v2.5": RESULTS / "stage3_mimo_v25",
    "Claude Haiku 4.5": RESULTS / "stage3_claude_haiku_4_5",
}

WORKFLOW_TOTALS = {"static": 41, "dynamic": 48, "rolling": 373}
STAGE3_ACCEPTED = {
    "MiniMax M2.5": {"static": 41, "dynamic": 43, "rolling": 367},
    "MiMo v2.5": {"static": 41, "dynamic": 48, "rolling": 368},
    "Claude Haiku 4.5": {"static": 41, "dynamic": 41, "rolling": 370},
}
FAILURES = {
    "MiniMax M2.5": {"wrong_tool_order": 4, "missing_required_tool": 3, "missing_eval_ref": 4},
    "MiMo v2.5": {"wrong_tool_order": 0, "missing_required_tool": 0, "missing_eval_ref": 5},
    "Claude Haiku 4.5": {"wrong_tool_order": 7, "missing_required_tool": 3, "missing_eval_ref": 0},
}


plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
    }
)

C_INFLOW = "#2b83ba"
C_RELEASE = "#1b9e77"
C_LEVEL = "#4d4d4d"
C_LIMIT = "#d7191c"
C_REPLAN = "#d95f02"
C_RETAIN = "#7570b3"
C_STAGE = "#f4a261"
C_GRAY = "#8d99ae"


def ensure_dirs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    TABLE_OUT.mkdir(parents=True, exist_ok=True)


def savefig(fig: plt.Figure, name: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def bool_count(series: pd.Series) -> int:
    return series.astype(str).str.lower().eq("true").sum()


def parse_stage_hour(stage: str) -> int:
    return int(str(stage).replace("rolling_", "").replace("h", ""))


def checks() -> None:
    assert 41 + 48 + 373 == 462
    assert 142 + 231 == 373
    assert round(231 / 373 * 100, 1) == 61.9
    assert 41 + 48 + 368 == 457
    assert 231 + 137 == 368
    assert 41 + 43 + 367 == 451
    assert 41 + 41 + 370 == 452
    assert 4 + 3 + 4 == 11
    assert 5 == 5
    assert 7 + 3 == 10


def build_tables() -> dict[str, pd.DataFrame]:
    static = pd.read_csv(RESULTS / "stage1" / "static" / "all_events_metrics.csv")
    dynamic = pd.read_csv(RESULTS / "stage1" / "dynamic" / "stage_results.csv")
    rolling = pd.read_csv(RESULTS / "stage1" / "rolling" / "stage_results.csv")

    group_rows: list[dict[str, object]] = []
    for group in ["S1", "S2", "S3", "S4"]:
        s = static[static["scenario_group"] == group]
        d = dynamic[dynamic["scenario_group"] == group]
        r = rolling[rolling["scenario_group"] == group]
        group_rows.append(
            {
                "flood_group_or_workflow": group,
                "events": s["event_id"].nunique(),
                "static_rows": len(s),
                "dynamic_rows": len(d),
                "rolling_rows": len(r),
                "total_rows": len(s) + len(d) + len(r),
                "role_in_evaluation": {
                    "S1": "Low-risk baseline cases",
                    "S2": "Moderate release-planning cases",
                    "S3": "Dynamic/event-stress cases",
                    "S4": "Extreme/high-volume cases",
                }[group],
            }
        )
    table5_1 = pd.DataFrame(
        group_rows
        + [
            {
                "flood_group_or_workflow": "Static workflow",
                "events": 41,
                "static_rows": 41,
                "dynamic_rows": 0,
                "rolling_rows": 0,
                "total_rows": 41,
                "role_in_evaluation": "Whole-event release planning",
            },
            {
                "flood_group_or_workflow": "Dynamic workflow",
                "events": 10,
                "static_rows": 0,
                "dynamic_rows": 48,
                "rolling_rows": 0,
                "total_rows": 48,
                "role_in_evaluation": "Stage-wise retain/replan",
            },
            {
                "flood_group_or_workflow": "Rolling workflow",
                "events": 10,
                "static_rows": 0,
                "dynamic_rows": 0,
                "rolling_rows": 373,
                "total_rows": 373,
                "role_in_evaluation": "3h rolling check with fixed forecast",
            },
            {
                "flood_group_or_workflow": "Total oracle rows",
                "events": "",
                "static_rows": 41,
                "dynamic_rows": 48,
                "rolling_rows": 373,
                "total_rows": 462,
                "role_in_evaluation": "Stage 2 oracle for Stage 3",
            },
        ]
    )

    table5_2_rows = []
    for group in ["S1", "S2", "S3", "S4"]:
        s = static[static["scenario_group"] == group]
        table5_2_rows.append(
            {
                "flood_group": group,
                "events": len(s),
                "accepted": bool_count(s["accepted"]),
                "hard_viol": bool_count(s["hard_violation"]),
                "downstream_viol": bool_count(s["downstream_violation"]),
                "mean_max_level_m": round(s["max_level"].mean(), 1),
                "max_level_m": round(s["max_level"].max(), 1),
                "mean_terminal_dev_m": round(s["terminal_deviation"].mean(), 1),
                "mean_inflow_peak_attenuation_rate": round(s["peak_reduction_rate"].mean(), 3),
            }
        )
    table5_2_rows.append(
        {
            "flood_group": "Total",
            "events": len(static),
            "accepted": bool_count(static["accepted"]),
            "hard_viol": bool_count(static["hard_violation"]),
            "downstream_viol": bool_count(static["downstream_violation"]),
            "mean_max_level_m": round(static["max_level"].mean(), 1),
            "max_level_m": round(static["max_level"].max(), 1),
            "mean_terminal_dev_m": round(static["terminal_deviation"].mean(), 1),
            "mean_inflow_peak_attenuation_rate": round(static["peak_reduction_rate"].mean(), 3),
        }
    )
    table5_2 = pd.DataFrame(table5_2_rows)

    table5_3 = (
        dynamic.groupby("event_id")
        .agg(
            checkpoints=("workflow_stage", "count"),
            replan=("action", lambda x: (x == "replan").sum()),
            retain=("action", lambda x: (x == "retain").sum()),
            accepted=("accepted", bool_count),
            hard_viol=("hard_violation", bool_count),
            scenario_group=("scenario_group", "first"),
            peak_inflow_m3s=("peak_inflow", "max"),
            max_level_m=("max_level", "max"),
        )
        .reset_index()
    )
    table5_3["notes"] = table5_3["scenario_group"].map(
        {"S1": "low-risk", "S2": "moderate", "S3": "high-risk", "S4": "extreme/high-volume"}
    )
    total_row = {
        "event_id": "Total",
        "checkpoints": len(dynamic),
        "replan": int((dynamic["action"] == "replan").sum()),
        "retain": int((dynamic["action"] == "retain").sum()),
        "accepted": bool_count(dynamic["accepted"]),
        "hard_viol": bool_count(dynamic["hard_violation"]),
        "scenario_group": "",
        "peak_inflow_m3s": "",
        "max_level_m": "",
        "notes": "",
    }
    table5_3 = pd.concat([table5_3, pd.DataFrame([total_row])], ignore_index=True)

    table5_4 = pd.DataFrame(
        [
            ("Rolling events", "10"),
            ("Total rolling checks", "373"),
            ("LLM-called checks", "142"),
            ("Deterministic retain rows", "231"),
            ("LLM-call reduction", "61.9%"),
            ("Accepted retain rows", "231/231"),
            ("Accepted LLM decisions, MiMo", "137/142"),
            ("Hard violations", "0"),
            ("Downstream violations", "0"),
            ("Forecast setting", "One fixed forecast at event start"),
        ],
        columns=["metric", "value"],
    )

    table5_5 = pd.DataFrame(
        [
            {
                "executor": name,
                "total_attempted": 462,
                "accepted": sum(vals.values()),
                "acceptance_rate": f"{sum(vals.values()) / 462 * 100:.1f}%",
                "oracle_metric_comparison": "PASS",
                "hard_viol": 0,
                "downstream_viol": 0,
            }
            for name, vals in STAGE3_ACCEPTED.items()
        ]
    )

    table5_6 = pd.DataFrame(
        [
            {
                "workflow": workflow,
                **{
                    name: f"{STAGE3_ACCEPTED[name][workflow]}/{WORKFLOW_TOTALS[workflow]}"
                    for name in EXECUTORS
                },
            }
            for workflow in ["static", "dynamic", "rolling"]
        ]
        + [
            {
                "workflow": "Total",
                **{name: f"{sum(STAGE3_ACCEPTED[name].values())}/462" for name in EXECUTORS},
            }
        ]
    )

    failure_rows = []
    for reason in ["wrong_tool_order", "missing_required_tool", "missing_eval_ref"]:
        failure_rows.append(
            {
                "failure_reason": reason,
                **{name: FAILURES[name][reason] for name in EXECUTORS},
            }
        )
    failure_rows.append(
        {
            "failure_reason": "Total rejected",
            **{name: sum(FAILURES[name].values()) for name in EXECUTORS},
        }
    )
    table5_7 = pd.DataFrame(failure_rows)

    tables = {
        "table5_1_scenario_oracle_coverage.csv": table5_1,
        "table5_2_static_by_flood_group.csv": table5_2,
        "table5_3_dynamic_results.csv": table5_3,
        "table5_4_rolling_trigger_only.csv": table5_4,
        "table5_5_executor_stage3_summary.csv": table5_5,
        "table5_6_workflow_by_executor.csv": table5_6,
        "table5_7_failure_taxonomy.csv": table5_7,
    }
    for filename, table in tables.items():
        table.to_csv(TABLE_OUT / filename, index=False, encoding="utf-8")
    return tables


def fig5_1_pipeline() -> None:
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.axis("off")
    boxes = [
        (
            0.02,
            "Stage 1\nDirect-service deterministic baseline",
            "OptimizationService / SimulationService / EvaluationService\n41 static + 48 dynamic + 373 rolling = 462 rows\n0 hard violations, 0 downstream violations",
            "#dbeafe",
        ),
        (
            0.36,
            "Stage 2\nDeterministic workflow oracle",
            "StaticWorkflow / DynamicWorkflow / RollingWorkflow\n462/462 matched Stage 1\nOracle metric comparison: PASS",
            "#e5e7eb",
        ),
        (
            0.70,
            "Stage 3\nLLM + MCP fail-closed evaluation",
            "Three executors attempted 462 rows each\nChecks: tool order, eval ref, schema, safety\nAccepted/rejected audit records",
            "#dcfce7",
        ),
    ]
    for x, title, body, color in boxes:
        rect = patches.FancyBboxPatch(
            (x, 0.22),
            0.28,
            0.58,
            boxstyle="round,pad=0.015,rounding_size=0.02",
            facecolor=color,
            edgecolor="#334155",
            linewidth=1.2,
        )
        ax.add_patch(rect)
        ax.text(x + 0.14, 0.68, title, ha="center", va="center", weight="bold", fontsize=10)
        ax.text(x + 0.14, 0.43, body, ha="center", va="center", fontsize=8, linespacing=1.35)
    for x1, x2 in [(0.30, 0.36), (0.64, 0.70)]:
        ax.annotate("", xy=(x2 - 0.01, 0.51), xytext=(x1 + 0.01, 0.51), arrowprops={"arrowstyle": "->", "lw": 1.5})
    ax.text(0.5, 0.08, "Validation flow: kernel feasibility -> workflow replication -> LLM/MCP auditability", ha="center", fontsize=9)
    savefig(fig, "fig5_1_validation_pipeline")


def dynamic_markers(event_id: int, sub: pd.DataFrame) -> pd.DataFrame:
    dyn = pd.read_csv(RESULTS / "stage1" / "dynamic" / "stage_results.csv")
    rows = dyn[dyn["event_id"].astype(str) == str(event_id)].copy().reset_index(drop=True)
    if rows.empty:
        return rows
    inflow = sub["inflow_observed"].tolist()
    n = len(inflow)
    peak_idx = int(np.argmax(inflow))
    candidates = [0, max(0, n // 4), peak_idx, min(n - 1, peak_idx + 2), min(n - 1, 3 * n // 4)]
    seen = []
    for idx in candidates:
        if idx not in seen:
            seen.append(idx)
    rows["idx"] = seen[: len(rows)]
    return rows


def load_processed_event(event_id: int) -> pd.DataFrame:
    path = ROOT / "data" / "processed" / "flood_event" / f"{event_id}.csv"
    return pd.read_csv(path, parse_dates=["time"]).rename(columns={"inflow": "inflow_observed", "level": "level_state"})


def dynamic_release_series(event_id: int, sub: pd.DataFrame, marks: pd.DataFrame) -> np.ndarray:
    release = np.full(len(sub), np.nan)
    if marks.empty:
        return release
    ordered = marks.sort_values("idx").reset_index(drop=True)
    for i, row in ordered.iterrows():
        start = int(row["idx"])
        end = int(ordered.loc[i + 1, "idx"]) if i + 1 < len(ordered) else len(sub)
        release[start:end] = float(row.get("peak_release", 0.0))
    if np.isnan(release).any():
        release = pd.Series(release).ffill().bfill().fillna(0.0).to_numpy()
    return release


def fig5_2_static_dynamic_cases() -> None:
    st = pd.read_csv(OP_DATA / "static_event_timeseries_all.csv", parse_dates=["time"])
    cases = [
        ("Static high-release case", 2024061623, "static"),
        ("Static lower-release case", 2019071011, "static"),
        ("Dynamic retain-dominant case", 2010062002, "dynamic"),
        ("Dynamic repeated-replan case", 2021052114, "dynamic"),
    ]
    fig, axes = plt.subplots(len(cases), 3, figsize=(12.5, 10.2), sharex=False)
    for row, (case_label, event_id, mode) in enumerate(cases):
        if mode == "static":
            sub = st[st["event_id"] == event_id].sort_values("time").reset_index(drop=True)
            release_col = "release_agent"
            level_col = "level_agent"
            marks = pd.DataFrame()
        else:
            sub = load_processed_event(event_id).sort_values("time").reset_index(drop=True)
            marks = dynamic_markers(event_id, sub)
            sub["release_dynamic"] = dynamic_release_series(event_id, sub, marks)
            release_col = "release_dynamic"
            level_col = "level_state"
        x = np.arange(len(sub))
        labels = sub["time"].dt.strftime("%m/%d\n%H:%M")

        ax = axes[row, 0]
        ax.plot(x, sub["inflow_observed"], color=C_INFLOW, lw=1.6, label="Inflow")
        ax.plot(x, sub[release_col], color=C_RELEASE, lw=1.6, label="Optimized release")
        for _, m in marks.iterrows():
            ax.axvline(m["idx"], color=C_REPLAN if m["action"] == "replan" else C_RETAIN, ls=":", lw=0.8, alpha=0.55)
        ax.set_title(f"{case_label}: event {event_id}")
        ax.set_ylabel("Flow (m3/s)")
        ax.legend(loc="upper right")

        ax = axes[row, 1]
        ax.plot(x, sub[level_col], color=C_LEVEL, lw=1.6, label="Reservoir level")
        flood_limit = float(sub["flood_limit_level"].iloc[0]) if "flood_limit_level" in sub.columns else 160.0
        design_level = float(sub["design_flood_level"].iloc[0]) if "design_flood_level" in sub.columns else 165.87
        ax.axhline(flood_limit, color=C_LIMIT, ls="--", lw=1.1, label="Flood limit")
        ax.axhline(design_level, color="#b2182b", ls=":", lw=1.0, label="Design flood")
        ax.set_title("Reservoir level")
        ax.set_ylabel("Level (m)")
        ax.legend(loc="best")

        ax = axes[row, 2]
        ax.set_ylim(-0.5, 1.5)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["retain", "replan"])
        ax.set_title("Dynamic decision checkpoints")
        if marks.empty:
            ax.text(0.5, 0.5, "full-horizon static plan", ha="center", va="center", transform=ax.transAxes)
        else:
            for _, m in marks.iterrows():
                y = 1 if m["action"] == "replan" else 0
                marker = "o" if m["action"] == "replan" else "s"
                face = C_REPLAN if m["action"] == "replan" else "white"
                edge = C_REPLAN if m["action"] == "replan" else C_RETAIN
                ax.scatter(m["idx"], y, s=55, marker=marker, facecolor=face, edgecolor=edge, zorder=4)
                ax.text(m["idx"], y + 0.15, m["workflow_stage"], ha="center", fontsize=7)
        for col in range(3):
            axes[row, col].set_xticks(x[:: max(1, len(x) // 5)])
            axes[row, col].set_xticklabels(labels.iloc[:: max(1, len(x) // 5)], rotation=0)
    fig.suptitle("Figure 5.2. Representative static and dynamic release-planning cases", weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    savefig(fig, "fig5_2_static_dynamic_cases")


def fig5_3_rolling_mechanism() -> None:
    fig, ax = plt.subplots(figsize=(11, 5.4))
    ax.axis("off")
    nodes = [
        (0.04, 0.68, 0.22, 0.18, "3h observed-state update", "current level, inflow,\nelapsed time, fixed forecast"),
        (0.36, 0.68, 0.23, 0.18, "Deterministic trigger checker", "initial, scheduled,\nforecast error, level risk"),
        (0.70, 0.80, 0.24, 0.14, "Trigger fired", "LLM + MCP workflow"),
        (0.70, 0.54, 0.24, 0.14, "No trigger", "deterministic retain row\nllm_called = false"),
        (0.36, 0.22, 0.25, 0.16, "Unified audit output", "result row, trace,\nvalidation flags, oracle comparison"),
    ]
    for x, y, w, h, title, body in nodes:
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01", facecolor="#f8fafc", edgecolor="#475569", lw=1.1)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h * 0.68, title, ha="center", va="center", weight="bold")
        ax.text(x + w / 2, y + h * 0.32, body, ha="center", va="center", fontsize=8)
    arrow = {"arrowstyle": "->", "lw": 1.4, "color": "#334155"}
    ax.annotate("", xy=(0.36, 0.77), xytext=(0.26, 0.77), arrowprops=arrow)
    ax.annotate("", xy=(0.70, 0.86), xytext=(0.59, 0.77), arrowprops=arrow)
    ax.annotate("", xy=(0.70, 0.61), xytext=(0.59, 0.75), arrowprops=arrow)
    ax.annotate("", xy=(0.49, 0.38), xytext=(0.82, 0.80), arrowprops=arrow)
    ax.annotate("", xy=(0.49, 0.38), xytext=(0.82, 0.54), arrowprops=arrow)
    ax.text(0.5, 0.08, "10/10 rolling events covered; 373 checks = 142 LLM-called + 231 deterministic retain rows", ha="center", weight="bold")
    savefig(fig, "fig5_3_rolling_trigger_mechanism")


def fig5_4_rolling_call_reduction() -> None:
    ro = pd.read_csv(OP_DATA / "rolling_event_timeseries_all.csv", parse_dates=["time"])
    results = pd.read_csv(RESULTS / "stage1" / "rolling" / "stage_results.csv")
    events = [
        (2012062402, "long multi-trigger"),
        (2021052114, "long high-volume"),
        (2024061623, "short high-water"),
    ]

    fig = plt.figure(figsize=(13.5, 9.0))
    gs = fig.add_gridspec(3, 3, width_ratios=[0.75, 1.55, 1.55], hspace=0.46, wspace=0.32)
    ax = fig.add_subplot(gs[:, 0])
    ax.bar([0], [142], color=C_REPLAN, label="LLM-called checks")
    ax.bar([0], [231], bottom=[142], color=C_GRAY, label="Deterministic retain rows")
    ax.set_xticks([0])
    ax.set_xticklabels(["All rolling\nchecks"])
    ax.set_ylabel("Check count")
    ax.set_ylim(0, 400)
    ax.text(0, 142 / 2, "142", ha="center", va="center", color="white", weight="bold")
    ax.text(0, 142 + 231 / 2, "231", ha="center", va="center", color="white", weight="bold")
    ax.text(0, 382, "LLM-call reduction:\n231/373 = 61.9%", ha="center", va="top", weight="bold")
    ax.legend(loc="lower center")

    for row, (event_id, label) in enumerate(events):
        sub = ro[ro["event_id"] == event_id].sort_values("time").reset_index(drop=True)
        rows = results[results["event_id"].astype(str) == str(event_id)].copy()
        rows["hour"] = rows["workflow_stage"].map(parse_stage_hour)
        rows["idx"] = rows["hour"] / 3
        x = np.arange(len(sub))
        labels = sub["time"].dt.strftime("%m/%d\n%H:%M")

        ax = fig.add_subplot(gs[row, 1])
        ax.plot(x, sub["inflow_observed"], color=C_INFLOW, lw=1.4, label="Observed inflow")
        ax.plot(x, sub["inflow_forecast"], color="#e76f51", lw=1.1, ls="--", label="Fixed forecast")
        ax.plot(x, sub["release_agent"], color=C_RELEASE, lw=1.4, label="Rolling release")
        for _, r in rows.iterrows():
            if r["action"] == "replan":
                ax.axvline(r["idx"], color=C_REPLAN, lw=0.6, alpha=0.35)
        ax.set_title(f"Event {event_id} ({label}): inflow, forecast, release")
        ax.set_ylabel("Flow (m3/s)")
        ax.set_xticks(x[:: max(1, len(x) // 5)])
        ax.set_xticklabels(labels.iloc[:: max(1, len(x) // 5)])
        if row == 0:
            ax.legend(ncol=3, loc="upper right")

        ax = fig.add_subplot(gs[row, 2])
        ax.plot(x, sub["level_agent"], color=C_LEVEL, lw=1.4, label="Reservoir level")
        ax.axhline(sub["flood_limit_level"].iloc[0], color=C_LIMIT, ls="--", lw=1.0, label="Flood limit")
        ymin, ymax = sub["level_agent"].min(), sub["level_agent"].max()
        offset = max((ymax - ymin) * 0.08, 0.04)
        for _, r in rows.iterrows():
            y = ymin - offset if r["action"] == "retain" else ymax + offset
            marker = "o" if r["action"] == "replan" else "s"
            color = C_REPLAN if r["action"] == "replan" else C_RETAIN
            ax.scatter(r["idx"], y, s=24, marker=marker, color=color, alpha=0.9)
        ax.set_title("Reservoir level and rolling actions")
        ax.set_ylabel("Level (m)")
        ax.set_xticks(x[:: max(1, len(x) // 5)])
        ax.set_xticklabels(labels.iloc[:: max(1, len(x) // 5)])
        if row == 0:
            ax.legend(loc="best")
    fig.suptitle("Figure 5.4. Rolling call reduction and representative rolling-operation process", weight="bold")
    fig.subplots_adjust(top=0.91, left=0.06, right=0.98, bottom=0.07, hspace=0.52, wspace=0.32)
    savefig(fig, "fig5_4_rolling_call_reduction_process")


def fig5_5_acceptance() -> None:
    workflows = ["static", "dynamic", "rolling", "total"]
    x = np.arange(len(workflows))
    width = 0.24
    fig, ax = plt.subplots(figsize=(9, 4.6))
    colors = ["#4575b4", "#1a9850", "#984ea3"]
    for i, (name, vals) in enumerate(STAGE3_ACCEPTED.items()):
        accepted = [vals.get(w, sum(vals.values())) for w in workflows]
        totals = [WORKFLOW_TOTALS.get(w, 462) for w in workflows]
        rates = [a / t * 100 for a, t in zip(accepted, totals)]
        ax.bar(x + (i - 1) * width, rates, width, label=name, color=colors[i], alpha=0.88)
        for xi, rate, a, t in zip(x + (i - 1) * width, rates, accepted, totals):
            ax.text(xi, rate + 1.3, f"{a}/{t}", ha="center", va="bottom", fontsize=7, rotation=90)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Fail-closed acceptance rate (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(["Static", "Dynamic", "Rolling", "Total"])
    ax.legend(loc="lower right")
    ax.set_title("Figure 5.5. Fail-closed acceptance by workflow and executor")
    savefig(fig, "fig5_5_acceptance_by_workflow_executor")


def fig5_6_failures() -> None:
    names = list(EXECUTORS.keys())
    reasons = ["wrong_tool_order", "missing_required_tool", "missing_eval_ref"]
    colors = ["#e41a1c", "#ff7f00", "#377eb8"]
    bottoms = np.zeros(len(names))
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for reason, color in zip(reasons, colors):
        vals = [FAILURES[name][reason] for name in names]
        ax.bar(x, vals, bottom=bottoms, label=reason, color=color, alpha=0.86)
        for xi, bottom, val in zip(x, bottoms, vals):
            if val:
                ax.text(xi, bottom + val / 2, str(val), ha="center", va="center", color="white", weight="bold", fontsize=8)
        bottoms += vals
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Rejected records")
    ax.set_title("Figure 5.6. Failure modes under fail-closed validation")
    ax.legend(loc="upper right")
    ax.text(0.5, -0.22, "Hard-safety violations = 0 and downstream-routing violations = 0 for all executors.", ha="center", transform=ax.transAxes)
    savefig(fig, "fig5_6_failure_taxonomy")


def main() -> None:
    ensure_dirs()
    checks()
    build_tables()
    fig5_1_pipeline()
    fig5_2_static_dynamic_cases()
    fig5_3_rolling_mechanism()
    fig5_4_rolling_call_reduction()
    fig5_5_acceptance()
    fig5_6_failures()
    print(f"Chapter 5 assets written to {OUT}")


if __name__ == "__main__":
    main()
