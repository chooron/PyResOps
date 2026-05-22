"""Generate Chapter 5 paper tables and figures.

Code lives under docs/paper/figures/chapter5/scripts/.
Generated assets are written under docs/paper/figures/chapter5/generated/.

Usage:
    python docs/paper/figures/generate_chapter5_results.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


CHAPTER5_DIR = Path(__file__).resolve().parent / "chapter5"
SCRIPT_DIR = CHAPTER5_DIR / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from _chapter5_common import (  # noqa: E402
    FAILURES,
    STAGE3_ACCEPTED,
    TABLE_OUT,
    WORKFLOW_TOTALS,
    bool_count,
    ensure_dirs,
    load_stage1_dynamic,
    load_stage1_rolling,
    read_csv,
)
import fig5_2_static_instruction_scenarios  # noqa: E402
import fig5_3_dynamic_command_multi_event  # noqa: E402
import fig5_4_rolling_call_reduction_process  # noqa: E402
import fig5_5_acceptance_by_workflow_executor  # noqa: E402
import fig5_6_failure_taxonomy  # noqa: E402
import fig5_4_wrongtest_forecast_error  # noqa: E402
import fig5_combined_acceptance_overview  # noqa: E402  ← 新增组合图


def _checks() -> None:
    assert 41 + 48 + 373 == 462
    assert 142 + 231 == 373
    assert round(231 / 373 * 100, 1) == 61.9
    assert 41 + 48 + 368 == 457
    assert 231 + 137 == 368
    assert 41 + 43 + 367 == 451
    assert 41 + 41 + 370 == 452


def build_tables() -> None:
    static = read_csv("experiments/results/stage1/static/all_events_metrics.csv")
    dynamic = load_stage1_dynamic()
    rolling = load_stage1_rolling()

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

    table5_1 = group_rows + [
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

    table5_2_rows: list[dict[str, object]] = []
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
    table5_3 = pd.concat(
        [
            table5_3,
            pd.DataFrame(
                [
                    {
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
                ]
            ),
        ],
        ignore_index=True,
    )

    table5_4 = [
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
    ]

    table5_5 = [
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

    table5_6 = [
        {
            "workflow": workflow,
            **{name: f"{STAGE3_ACCEPTED[name][workflow]}/{WORKFLOW_TOTALS[workflow]}" for name in STAGE3_ACCEPTED},
        }
        for workflow in ["static", "dynamic", "rolling"]
    ] + [
        {"workflow": "Total", **{name: f"{sum(STAGE3_ACCEPTED[name].values())}/462" for name in STAGE3_ACCEPTED}}
    ]

    failure_rows = [
        {"failure_reason": reason, **{name: FAILURES[name][reason] for name in STAGE3_ACCEPTED}}
        for reason in ["wrong_tool_order", "missing_required_tool", "missing_eval_ref"]
    ]
    failure_rows.append(
        {"failure_reason": "Total rejected", **{name: sum(FAILURES[name].values()) for name in STAGE3_ACCEPTED}}
    )

    tables = {
        "table5_1_scenario_oracle_coverage.csv": pd.DataFrame(table5_1),
        "table5_2_static_by_flood_group.csv": pd.DataFrame(table5_2_rows),
        "table5_3_dynamic_results.csv": table5_3,
        "table5_4_rolling_trigger_only.csv": pd.DataFrame(table5_4, columns=["metric", "value"]),
        "table5_5_executor_stage3_summary.csv": pd.DataFrame(table5_5),
        "table5_6_workflow_by_executor.csv": pd.DataFrame(table5_6),
        "table5_7_failure_taxonomy.csv": pd.DataFrame(failure_rows),
    }
    for filename, table in tables.items():
        table.to_csv(TABLE_OUT / filename, index=False, encoding="utf-8")
        print(f"Saved: {TABLE_OUT / filename}")


def main() -> None:
    ensure_dirs()
    _checks()
    build_tables()
    fig5_2_static_instruction_scenarios.generate()
    fig5_3_dynamic_command_multi_event.generate()
    fig5_4_rolling_call_reduction_process.generate()
    fig5_5_acceptance_by_workflow_executor.generate()
    fig5_6_failure_taxonomy.generate()
    fig5_4_wrongtest_forecast_error.generate()
    # ↓ 新增：生成改进布局的四面板组合图
    fig5_combined_acceptance_overview.generate()
    print(f"Chapter 5 generated assets written under {CHAPTER5_DIR / 'generated'}")


if __name__ == "__main__":
    main()