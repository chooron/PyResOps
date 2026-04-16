"""
动态调整场景实验模块（阶段推进版）

核心原则：
1. 每个场景按触发时间轴分阶段执行，不再使用旧的 round 累积模型。
2. 每个阶段之间通过水量平衡推进状态，下一阶段看到的是真实演变后的状态。
3. 评估指标以“本次指令是否达标”为主，同时保留旧接口所需的兼容字段。
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.scenario_config import get_dynamic_triggers, get_scenarios
from experiments.evaluation_metrics import (
    DynamicAdjustmentEvaluator,
    _build_tankan_spec,
    _run_pyresops_eval,
    evaluate_instruction_compliance,
)

_dyn_eval = DynamicAdjustmentEvaluator()


DYNAMIC_TRIGGERS: dict[str, list[dict]] = get_dynamic_triggers()


ALL_SCENARIO_IDS = ["S01", "S02", "S03", "S04", "S05"]

RESULTS_DIR = Path(__file__).parent / "results"
STATIC_RESULTS_DIR = RESULTS_DIR / "static"
DYNAMIC_RESULTS_DIR = RESULTS_DIR / "dynamic"


# ============================================================
# 内部工具函数
# ============================================================


def _get_scenarios() -> dict[str, dict]:
    return get_scenarios()


def _get_state_dict(scenario: dict, outflow: float | None = None) -> dict:
    return {
        "level": float(scenario["current_level"]),
        "storage": float(scenario["initial_storage"]),
        "inflow": float(scenario["initial_inflow"]),
        "outflow": float(scenario["initial_inflow"] if outflow is None else outflow),
    }


def _stage_advance_hours(scenario: dict, triggers: list[dict], index: int) -> int:
    current = triggers[index]
    if index + 1 < len(triggers):
        return max(0, triggers[index + 1]["trigger_hours"] - current["trigger_hours"])
    return max(0, scenario["duration_hours"] - current["trigger_hours"])


def _apply_trigger(scenario: dict, trigger: dict, state_dict: dict | None = None) -> dict:
    adjusted = scenario.copy()
    if state_dict is not None:
        adjusted["current_level"] = float(state_dict["level"])
        adjusted["initial_storage"] = float(state_dict["storage"])
        adjusted["initial_inflow"] = float(state_dict["inflow"])

    pass_condition = trigger.get("pass_condition", {})
    if pass_condition.get("type") == "level_target":
        adjusted["target_level"] = float(pass_condition["target"])

    adjusted["dynamic_stage"] = trigger["stage"]
    adjusted["dynamic_trigger"] = trigger["natural_lang"]
    adjusted["trigger_type"] = trigger["type"]
    adjusted["description"] = (
        f"{scenario['description']}\n\n[{trigger['stage']}] {trigger['natural_lang']}"
    )
    return adjusted


def _eval_scenario(scenario: dict, outflow: float) -> dict:
    spec = _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))
    return _run_pyresops_eval(scenario, outflow, spec)


def _advance_state(scenario: dict, outflow: float, advance_hours: int) -> dict:
    """
    纯函数：用常数出库流量做水量平衡推进，返回阶段末态。

    注意：advance_hours 不是 time_step_hours 的整数倍时按向下取整处理。
    """
    spec = _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))
    step_hours = int(scenario["time_step_hours"])
    if step_hours <= 0:
        raise ValueError("time_step_hours 必须大于 0")

    n_steps = max(0, int(advance_hours) // step_hours)
    storage = float(scenario["initial_storage"])
    inflow = float(scenario["inflow"])
    if n_steps == 0:
        return {
            "level": round(float(scenario["current_level"]), 3),
            "storage": round(storage, 4),
            "inflow": float(scenario["initial_inflow"]),
            "outflow": float(outflow),
        }

    dead_storage = max(13.94, spec.level_storage_curve.get_storage(spec.dead_level))
    step_seconds = step_hours * 3600

    for _ in range(n_steps):
        storage += (inflow - outflow) * step_seconds / 1e8
        storage = max(storage, dead_storage)

    level = spec.level_storage_curve.get_level(storage)
    return {
        "level": round(level, 3),
        "storage": round(storage, 4),
        "inflow": inflow,
        "outflow": float(outflow),
    }


def _build_compat_summary(
    scenario_id: str,
    scenario_name: str,
    stages_summary: dict,
) -> dict:
    stages = stages_summary.get("stages", [])
    first_stage = stages[0] if stages else {}
    first_eval = first_stage.get("evaluation", {})
    first_compliance = first_stage.get("compliance", {})
    state_before = first_stage.get("state_before", {})
    llm_outflow = float(first_stage.get("llm_outflow", 0.0))
    before_outflow = float(state_before.get("outflow", llm_outflow))
    before_eval = {
        "constraint_violations": 0,
        "overall_score": 0.0,
    }
    before_rate = _dyn_eval.compute_constraint_achievement_rate(before_eval)
    after_rate = _dyn_eval.compute_constraint_achievement_rate(first_eval)
    trend = _dyn_eval.assess_adjustment_effectiveness(before_rate, after_rate)

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "overall_pass_rate": stages_summary.get("overall_pass_rate", 0.0),
        "stage_pass_count": stages_summary.get("stage_pass_count", 0),
        "stage_total": stages_summary.get("stage_total", 0),
        "hard_task_partial_credits": stages_summary.get("hard_task_partial_credits", {}),
        "adjustment_effective": bool(first_compliance.get("pass", False)),
        "constraint_achievement_rate": {
            "before": before_rate,
            "after": after_rate,
            "trend": trend,
        },
        "adjustment_delta": {
            "outflow_delta": round(llm_outflow - before_outflow, 1),
        },
        "score_change": round(first_eval.get("overall_score", 0.0), 4),
        "stages": stages,
    }


def _build_static_instruction(scenario: dict) -> str:
    return (
        f"Static baseline dispatch for {scenario['id']} ({scenario['name']}): "
        f"analyze current state and provide one-shot release recommendation."
    )


def _derive_tool_calls_detail(result: dict) -> list[dict]:
    existing = result.get("tool_calls_detail")
    if isinstance(existing, list) and existing:
        derived: list[dict] = []
        for idx, item in enumerate(existing, 1):
            if isinstance(item, dict):
                derived.append(
                    {
                        "call_order": int(item.get("call_order", idx)),
                        "tool_name": str(item.get("tool_name", "unknown")),
                    }
                )
        if derived:
            return derived

    trace = result.get("llm_execution_trace", {})
    events = trace.get("tool_events", []) if isinstance(trace, dict) else []
    if isinstance(events, list) and events:
        derived = []
        for idx, event in enumerate(events, 1):
            if not isinstance(event, dict):
                continue
            derived.append(
                {
                    "call_order": int(event.get("call_order", idx)),
                    "tool_name": str(event.get("tool_name", "unknown")),
                }
            )
        if derived:
            return derived

    chain = result.get("tool_call_chain", [])
    if isinstance(chain, list):
        return [
            {
                "call_order": idx,
                "tool_name": str(tool_name),
            }
            for idx, tool_name in enumerate(chain, 1)
        ]

    return []


# ============================================================
# 静态基线（无触发）
# ============================================================


def run_static_baseline(
    scenario_id: str,
    experiment=None,
    model_profile: str | None = None,
    scenario_override: dict | None = None,
    save_result: bool = True,
) -> dict:
    """
    运行单个场景的静态基线（无动态触发事件）。
    结果保存到 results/static/{scenario_id}_baseline.json。
    """
    scenarios_map = _get_scenarios()
    scenario = (
        scenario_override.copy() if scenario_override is not None else scenarios_map[scenario_id]
    )
    if scenario.get("id") == "S01":
        scenario.setdefault("agent_workflow_profile", "static_s01_mcp_chain_v1")

    if experiment is None:
        from pyresops.agents import ReservoirAgentRuntime

        experiment = ReservoirAgentRuntime(model_profile=model_profile)

    print(f"\n[静态基线] {scenario_id} - {scenario['name']}")
    mcp_result = experiment.run_scenario(scenario)
    outflow = float(mcp_result.get("outflow", scenario["inflow"]))
    tool_call_chain = list(mcp_result.get("tool_call_chain", []))
    llm_execution_trace = mcp_result.get("llm_execution_trace", {})
    accepted_pair = mcp_result.get("accepted_evidence_pair")
    simulation_event = (
        accepted_pair.get("simulation", {}) if isinstance(accepted_pair, dict) else {}
    )
    evaluation_event = (
        accepted_pair.get("evaluation", {}) if isinstance(accepted_pair, dict) else {}
    )
    sim_payload = (
        simulation_event.get("result_payload", {}) if isinstance(simulation_event, dict) else {}
    )
    eval_payload = (
        evaluation_event.get("result_payload", {}) if isinstance(evaluation_event, dict) else {}
    )
    eval_dict = _eval_scenario(scenario, outflow)

    score_overall = eval_payload.get("overall_score")
    score_flood = eval_payload.get("flood_control_score")
    score_supply = eval_payload.get("water_supply_score")
    score_power = eval_payload.get("power_generation_score")
    score_eco = eval_payload.get("ecological_score")
    if not isinstance(score_overall, (int, float)):
        score_overall = eval_dict["overall_score"]
    if not isinstance(score_flood, (int, float)):
        score_flood = eval_dict["flood_control_score"]
    if not isinstance(score_supply, (int, float)):
        score_supply = eval_dict["water_supply_score"]
    if not isinstance(score_power, (int, float)):
        score_power = eval_dict["power_generation_score"]
    if not isinstance(score_eco, (int, float)):
        score_eco = eval_dict["ecological_score"]

    sim_details = {
        "simulation": sim_payload if isinstance(sim_payload, dict) else {},
        "evaluation": eval_payload if isinstance(eval_payload, dict) else {},
    }

    tool_calls_detail = _derive_tool_calls_detail(mcp_result)

    result = {
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "type": "static_baseline",
        "instruction": _build_static_instruction(scenario),
        "outflow": outflow,
        "scores": {
            "overall": score_overall,
            "flood_control": score_flood,
            "water_supply": score_supply,
            "power": score_power,
            "ecological": score_eco,
        },
        "constraint_violations": eval_dict["constraint_violations"],
        "constraint_achievement_rate": _dyn_eval.compute_constraint_achievement_rate(eval_dict),
        "tool_call_count": mcp_result.get("tool_call_count", 0),
        "tool_call_chain": tool_call_chain,
        "tool_calls_detail": tool_calls_detail,
        "total_tool_calls": mcp_result.get("tool_call_count", 0),
        "total_time_seconds": mcp_result.get("total_time_seconds", 0.0),
        "final_decision_text": mcp_result.get("final_decision_text", ""),
        "llm_execution_trace": llm_execution_trace,
        "accepted_attempt_index": mcp_result.get("accepted_attempt_index"),
        "acceptance_failure_reason": mcp_result.get("acceptance_failure_reason"),
        "success": mcp_result.get("success", False),
        "sim_details": sim_details,
        "diagnostic_eval_summary": {k: v for k, v in eval_dict.items() if k.startswith("sim_")},
    }

    if save_result:
        STATIC_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = STATIC_RESULTS_DIR / f"{scenario_id}_baseline.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  基线结果已保存: {out_path}")

    return result


# ============================================================
# 阶段式动态实验
# ============================================================


def run_multi_round_dynamic_experiment(
    scenario_id: str,
    max_rounds: int | None = None,
    experiment=None,
    model_profile: str | None = None,
    scenario_override: dict | None = None,
    save_result: bool = True,
) -> dict:
    """
    运行单个场景的阶段式动态实验。

    Args:
        scenario_id: 场景 ID。
        max_rounds: 最多执行阶段数；None 或 <=0 时执行该场景的全部阶段。
    """
    if scenario_id not in DYNAMIC_TRIGGERS:
        raise ValueError(f"场景 {scenario_id} 未定义动态触发事件")

    scenarios_map = _get_scenarios()
    scenario = (
        scenario_override.copy()
        if scenario_override is not None
        else scenarios_map[scenario_id].copy()
    )
    triggers = DYNAMIC_TRIGGERS[scenario_id]
    if max_rounds is None or max_rounds <= 0:
        stage_total = len(triggers)
    else:
        stage_total = min(max_rounds, len(triggers))

    if experiment is None:
        from pyresops.agents import ReservoirAgentRuntime

        experiment = ReservoirAgentRuntime(model_profile=model_profile)

    print(f"\n{'=' * 60}")
    print(f"阶段式动态实验：{scenario_id} - {scenario['name']}（共{stage_total}阶段）")
    print(f"{'=' * 60}")

    current_state = _get_state_dict(scenario)
    total_tool_calls = 0
    all_tool_call_chain: list[str] = []
    stage_pass_count = 0
    hard_task_partial_credits: dict[str, float] = {}
    stages: list[dict] = []

    for index, trigger in enumerate(triggers[:stage_total]):
        advance_hours = _stage_advance_hours(scenario, triggers, index)
        stage_scenario = scenario.copy()
        stage_scenario["duration_hours"] = max(
            stage_scenario["time_step_hours"],
            advance_hours,
        )
        stage_scenario = _apply_trigger(stage_scenario, trigger, state_dict=current_state)

        print(
            f"[阶段 {trigger['stage']}] t={trigger['trigger_hours']}h, "
            f"推进窗口={advance_hours}h: {trigger['description']}"
        )

        llm_result = experiment.run_scenario(stage_scenario)
        llm_outflow = float(llm_result.get("outflow", stage_scenario["inflow"]))
        stage_tool_call_chain = llm_result.get("tool_call_chain", [])
        total_tool_calls += llm_result.get("tool_call_count", 0)
        all_tool_call_chain.extend(stage_tool_call_chain)

        stage_eval = _eval_scenario(stage_scenario, llm_outflow)
        state_after_sim = _advance_state(stage_scenario, llm_outflow, advance_hours)
        compliance = evaluate_instruction_compliance(
            trigger=trigger,
            llm_outflow=llm_outflow,
            state_before=current_state,
            state_after_sim=state_after_sim,
        )

        stage_pass_count += int(compliance["pass"])
        if compliance.get("is_hard_task"):
            hard_task_partial_credits[trigger["stage"]] = compliance["partial_credit"]

        stage_record = {
            "stage": trigger["stage"],
            "trigger_hours": trigger["trigger_hours"],
            "sim_hours_before": trigger["sim_hours_before"],
            "instruction": trigger["natural_lang"],
            "state_before": current_state.copy(),
            "llm_outflow": llm_outflow,
            "compliance": compliance,
            "state_after_sim": state_after_sim,
            "evaluation": stage_eval,
            "tool_call_count": llm_result.get("tool_call_count", 0),
            "tool_call_chain": stage_tool_call_chain,
            "total_time_seconds": llm_result.get("total_time_seconds", 0.0),
            "final_decision_text": llm_result.get("final_decision_text", ""),
            "llm_execution_trace": llm_result.get("llm_execution_trace", {}),
        }
        stages.append(stage_record)

        current_state = state_after_sim

    summary = {
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "stages": stages,
        "overall_pass_rate": round(stage_pass_count / stage_total, 4) if stage_total else 0.0,
        "stage_pass_count": stage_pass_count,
        "stage_total": stage_total,
        "hard_task_partial_credits": hard_task_partial_credits,
        "total_tool_calls": total_tool_calls,
        "tool_call_chain": all_tool_call_chain,
    }

    if save_result:
        DYNAMIC_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stages_path = DYNAMIC_RESULTS_DIR / f"{scenario_id}_stages.json"
        with open(stages_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        compat_summary = _build_compat_summary(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            stages_summary=summary,
        )
        summary_path = DYNAMIC_RESULTS_DIR / f"{scenario_id}_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(compat_summary, f, ensure_ascii=False, indent=2)

        print(f"  阶段结果已保存: {stages_path}")
        print(f"  兼容汇总已保存: {summary_path}")

    return summary


# ============================================================
# 批量入口
# ============================================================


def run_all_static_baselines(
    scenario_ids: list[str] | None = None,
    model_profile: str | None = None,
) -> list[dict]:
    """运行所有场景的静态基线（无触发），结果保存到 results/static/。"""
    ids = scenario_ids or ALL_SCENARIO_IDS
    from pyresops.agents import ReservoirAgentRuntime

    experiment = ReservoirAgentRuntime(model_profile=model_profile)
    results = []
    for sid in ids:
        try:
            results.append(run_static_baseline(sid, experiment=experiment, save_result=True))
        except Exception as exc:  # pragma: no cover - batch resilience path
            print(f"  ✗ {sid} 静态基线失败: {exc}")
            results.append({"scenario_id": sid, "error": str(exc), "success": False})
    return results


def run_all_multi_round(
    scenario_ids: list[str] | None = None,
    max_rounds: int = 4,
    model_profile: str | None = None,
) -> list[dict]:
    """运行所有场景的阶段式动态实验，结果保存到 results/dynamic/。"""
    ids = scenario_ids or ALL_SCENARIO_IDS
    from pyresops.agents import ReservoirAgentRuntime

    experiment = ReservoirAgentRuntime(model_profile=model_profile)
    results = []
    for sid in ids:
        try:
            results.append(
                run_multi_round_dynamic_experiment(
                    sid,
                    max_rounds=max_rounds,
                    experiment=experiment,
                    save_result=True,
                )
            )
        except Exception as exc:  # pragma: no cover - batch resilience path
            print(f"  ✗ {sid} 动态实验失败: {exc}")
            results.append({"scenario_id": sid, "error": str(exc), "success": False})
    return results


# ============================================================
# 兼容旧接口（供 paper_experiment_runner.run_all 调用）
# ============================================================


def run_dynamic_experiments(
    scenario_ids: list[str] | None = None,
    model_profile: str | None = None,
) -> list[dict]:
    """
    兼容旧接口：保留返回字段，但内部复用新版阶段式动态实验。
    """
    ids = scenario_ids or ["S01", "S02", "S03"]
    scenarios_map = _get_scenarios()

    from pyresops.agents import ReservoirAgentRuntime

    experiment = ReservoirAgentRuntime(model_profile=model_profile)

    results = []
    for sid in ids:
        try:
            scenario = scenarios_map[sid]
            baseline_mcp = experiment.run_scenario(scenario)
            baseline_outflow = float(baseline_mcp.get("outflow", scenario["inflow"]))
            baseline_eval = _eval_scenario(scenario, baseline_outflow)

            summary = run_multi_round_dynamic_experiment(
                sid,
                max_rounds=1,
                experiment=experiment,
                save_result=True,
            )
            stage = summary["stages"][0]
            after_eval = stage.get("evaluation", {})
            before_rate = _dyn_eval.compute_constraint_achievement_rate(baseline_eval)
            after_rate = _dyn_eval.compute_constraint_achievement_rate(after_eval)
            trend = _dyn_eval.assess_adjustment_effectiveness(before_rate, after_rate)

            results.append(
                {
                    "scenario_id": sid,
                    "adjustment_effective": after_rate >= before_rate,
                    "constraint_achievement_rate": {
                        "before": before_rate,
                        "after": after_rate,
                        "trend": trend,
                    },
                    "adjustment_delta": {
                        "outflow_delta": round(stage["llm_outflow"] - baseline_outflow, 1),
                    },
                    "score_change": round(
                        after_eval.get("overall_score", 0.0)
                        - baseline_eval.get("overall_score", 0.0),
                        4,
                    ),
                    "overall_pass_rate": summary["overall_pass_rate"],
                    "hard_task_partial_credits": summary.get("hard_task_partial_credits", {}),
                    "stages": summary["stages"],
                }
            )
        except Exception as exc:  # pragma: no cover - batch resilience path
            results.append({"scenario_id": sid, "error": str(exc)})
    return results


if __name__ == "__main__":
    import sys

    scenario_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    print("=" * 60)
    print("阶段式动态实验（所有场景）")
    print("=" * 60)
    results = run_all_multi_round(scenario_ids=scenario_ids, max_rounds=4)
    print(f"\n{'=' * 60}")
    print(f"实验完成，共 {len(results)} 个场景")
    for result in results:
        if "error" in result:
            print(f"  {result['scenario_id']}: 失败 - {result['error']}")
            continue
        print(
            f"  {result['scenario_id']}: "
            f"{result['stage_pass_count']}/{result['stage_total']} 通过, "
            f"overall_pass_rate={result['overall_pass_rate']:.2%}"
        )
