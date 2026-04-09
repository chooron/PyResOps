"""
动态调整场景实验模块（多轮触发版）

支持 5 个场景（S01~S05）全部动态化，每个场景定义 3 个顺序触发事件。
每次实验可选择运行 1/2/3 轮，每轮累积触发前 N 个事件，体现动态调整优越性。

核心流程（以 Round 2 为例）：
  Phase 0: 静态基线（无触发）→ 记录 baseline_score
  Phase 1: 初始调度 → 触发事件1 → LLM调整 → 评估
  Phase 2: 在 Phase1 基础上 → 触发事件2 → LLM调整 → 评估
  ...
  最终输出：rounds 对比表（trigger_count / final_score / constraint_rate / tool_calls）
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

try:
    from evaluation_metrics import DynamicAdjustmentEvaluator, _build_tankan_spec, _run_pyresops_eval
except ModuleNotFoundError:
    from experiments.evaluation_metrics import DynamicAdjustmentEvaluator, _build_tankan_spec, _run_pyresops_eval

_dyn_eval = DynamicAdjustmentEvaluator()

# ============================================================
# 每个场景 3 个顺序触发事件
# ============================================================

DYNAMIC_TRIGGERS: dict[str, list[dict]] = {
    "S01": [
        {
            "round": 1,
            "type": "forecast_deviation",
            "description": "实际入库流量超出预报值50%，达450 m³/s",
            "natural_lang": (
                "预报偏差超阈值：实际入库流量450 m³/s，超预报300 m³/s的50%，"
                "需重新评估泄洪策略"
            ),
            "adjusted_inflow": 450.0,
        },
        {
            "round": 2,
            "type": "instruction_change",
            "description": "上级指令：加大预泄，出库目标提升至600 m³/s",
            "natural_lang": (
                "上级防汛指令变更：要求加大预泄力度，出库流量目标提升至600 m³/s，"
                "请调整调度方案"
            ),
            "adjusted_inflow": 450.0,
        },
        {
            "round": 3,
            "type": "typhoon_track_shift",
            "description": "台风路径偏移，入库流量进一步升至700 m³/s",
            "natural_lang": (
                "台风路径偏移预警：最新气象预报显示入库流量将升至700 m³/s，"
                "需进一步加大预泄"
            ),
            "adjusted_inflow": 700.0,
        },
    ],
    "S02": [
        {
            "round": 1,
            "type": "instruction_change",
            "description": "鹤城站控制流量上限由14000降至12000 m³/s",
            "natural_lang": (
                "上级防汛指令变更：鹤城站控制流量上限由14000降至12000 m³/s，"
                "请调整错峰调度方案"
            ),
            "adjusted_inflow": None,
        },
        {
            "round": 2,
            "type": "window_shrink",
            "description": "错峰调度窗口从48h缩短至24h",
            "natural_lang": (
                "调度窗口压缩：上级要求错峰下泄窗口从48小时缩短至24小时，"
                "需重新制定分时下泄计划"
            ),
            "adjusted_inflow": None,
        },
        {
            "round": 3,
            "type": "inflow_surge",
            "description": "区间暴雨，入库流量突增至5000 m³/s",
            "natural_lang": (
                "紧急预警：上游区间暴雨导致入库流量突增至5000 m³/s，"
                "超原预报3380 m³/s，需立即调整错峰方案"
            ),
            "adjusted_inflow": 5000.0,
        },
    ],
    "S03": [
        {
            "round": 1,
            "type": "emergency_flood",
            "description": "入库流量突破设计洪水，达12000 m³/s",
            "natural_lang": (
                "紧急预警：实测入库流量达12000 m³/s，超设计洪水（8000），"
                "启动超标准洪水应急预案"
            ),
            "adjusted_inflow": 12000.0,
        },
        {
            "round": 2,
            "type": "dam_monitoring_alert",
            "description": "大坝监测异常，最大泄量限制至8000 m³/s",
            "natural_lang": (
                "大坝安全预警：坝体监测出现异常渗流，工程师建议将最大泄量限制至"
                "8000 m³/s，请在此约束下重新制定应急方案"
            ),
            "adjusted_inflow": 12000.0,
        },
        {
            "round": 3,
            "type": "downstream_levee_risk",
            "description": "下游堤防险情，需紧急减泄至6000 m³/s以内",
            "natural_lang": (
                "下游险情：鹤城段堤防出现管涌险情，防汛指挥部要求出库流量立即"
                "降至6000 m³/s以内，请紧急调整应急调度方案"
            ),
            "adjusted_inflow": 12000.0,
        },
    ],
    "S04": [
        {
            "round": 1,
            "type": "inflow_surge",
            "description": "枯水期来水突增：入库从70升至250 m³/s",
            "natural_lang": (
                "来水突增预警：上游降雨导致入库流量从70 m³/s突增至250 m³/s，"
                "枯水期发电计划需重新优化"
            ),
            "adjusted_inflow": 250.0,
        },
        {
            "round": 2,
            "type": "grid_dispatch_change",
            "description": "电网调度要求增加出力，额定发电流量400 m³/s",
            "natural_lang": (
                "电网调度指令：电网负荷高峰，要求水电站按额定流量400 m³/s满发，"
                "请调整发电调度方案"
            ),
            "adjusted_inflow": 250.0,
        },
        {
            "round": 3,
            "type": "level_warning",
            "description": "水位跌至警戒线135m，需切换保护水位模式",
            "natural_lang": (
                "水位预警：当前水位接近135m警戒线，按规程需降低出力保护水位，"
                "请调整为保护水位调度模式"
            ),
            "adjusted_inflow": 250.0,
        },
    ],
    "S05": [
        {
            "round": 1,
            "type": "instruction_accelerate",
            "description": "上级指令加快降水位，从3天缩短至2天内完成",
            "natural_lang": (
                "上级指令变更：要求梅台过渡期降水位操作从3天压缩至2天内完成，"
                "请加大出库流量重新制定降水位方案"
            ),
            "adjusted_inflow": None,
        },
        {
            "round": 2,
            "type": "downstream_incident",
            "description": "下游出现险情，出库流量限制≤800 m³/s",
            "natural_lang": (
                "下游险情通报：下游河道出现险情，防汛指挥部要求出库流量控制在"
                "800 m³/s以内，请在此约束下重新制定降水位方案"
            ),
            "adjusted_inflow": None,
        },
        {
            "round": 3,
            "type": "typhoon_early_warning",
            "description": "台风预报提前，需在24h内完成预泄至156.5m",
            "natural_lang": (
                "台风预报提前：最新气象预报显示台风将提前12小时登陆，"
                "要求在24小时内将水位从当前降至156.5m，请制定紧急预泄方案"
            ),
            "adjusted_inflow": 500.0,
        },
    ],
}

ALL_SCENARIO_IDS = ["S01", "S02", "S03", "S04", "S05"]

RESULTS_DIR = Path(__file__).parent / "results"
STATIC_RESULTS_DIR = RESULTS_DIR / "static"
DYNAMIC_RESULTS_DIR = RESULTS_DIR / "dynamic"


# ============================================================
# 内部工具函数
# ============================================================

def _get_scenarios() -> dict[str, dict]:
    from paper_experiment_runner import SCENARIOS
    return {s["id"]: s for s in SCENARIOS}


def _apply_trigger(scenario: dict, trigger: dict) -> dict:
    adjusted = scenario.copy()
    if trigger.get("adjusted_inflow") is not None:
        adjusted["inflow"] = trigger["adjusted_inflow"]
        adjusted["initial_inflow"] = trigger["adjusted_inflow"]
    adjusted["dynamic_trigger"] = trigger["natural_lang"]
    adjusted["trigger_type"] = trigger["type"]
    adjusted["description"] = (
        f"【动态调整 Round{trigger['round']}】{scenario['description']} | "
        f"触发：{trigger['natural_lang']}"
    )
    return adjusted


def _eval_scenario(scenario: dict, outflow: float) -> dict:
    spec = _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))
    return _run_pyresops_eval(scenario, outflow, spec)


# ============================================================
# 静态基线（无触发）
# ============================================================

def run_static_baseline(
    scenario_id: str,
    experiment=None,
    model_profile: str | None = None,
    save_result: bool = True,
) -> dict:
    """
    运行单个场景的静态基线（无动态触发事件）。
    结果保存到 results/static/{scenario_id}_baseline.json。
    """
    scenarios_map = _get_scenarios()
    scenario = scenarios_map[scenario_id]

    if experiment is None:
        from paper_experiment_runner import AgnoMCPExperiment
        experiment = AgnoMCPExperiment(model_profile=model_profile)

    print(f"\n[静态基线] {scenario_id} - {scenario['name']}")
    mcp_result = experiment.run_scenario(scenario)
    outflow = mcp_result.get("outflow", scenario["inflow"])
    eval_dict = _eval_scenario(scenario, outflow)

    result = {
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "type": "static_baseline",
        "outflow": outflow,
        "scores": {
            "overall": eval_dict["overall_score"],
            "flood_control": eval_dict["flood_control_score"],
            "water_supply": eval_dict["water_supply_score"],
            "power": eval_dict["power_generation_score"],
            "ecological": eval_dict["ecological_score"],
        },
        "constraint_violations": eval_dict["constraint_violations"],
        "constraint_achievement_rate": _dyn_eval.compute_constraint_achievement_rate(eval_dict),
        "tool_call_count": mcp_result.get("tool_call_count", 0),
        "total_time_seconds": mcp_result.get("total_time_seconds", 0.0),
        "success": mcp_result.get("success", False),
        "sim_details": {k: v for k, v in eval_dict.items() if k.startswith("sim_")},
    }

    if save_result:
        STATIC_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = STATIC_RESULTS_DIR / f"{scenario_id}_baseline.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  基线结果已保存: {out_path}")

    return result


# ============================================================
# 多轮动态实验
# ============================================================

def run_multi_round_dynamic_experiment(
    scenario_id: str,
    max_rounds: int = 3,
    experiment=None,
    model_profile: str | None = None,
    save_result: bool = True,
) -> dict:
    """
    运行单个场景的多轮动态实验（1/2/3 次触发对比）。

    每轮从初始状态出发，累积触发前 N 个事件，LLM 逐次调整。
    结果保存到 results/dynamic/{scenario_id}_round{n}.json。

    Returns:
        包含 baseline_score、rounds 对比表的汇总字典
    """
    if scenario_id not in DYNAMIC_TRIGGERS:
        raise ValueError(f"场景 {scenario_id} 未定义动态触发事件")

    scenarios_map = _get_scenarios()
    scenario = scenarios_map[scenario_id]
    triggers = DYNAMIC_TRIGGERS[scenario_id]
    max_rounds = min(max_rounds, len(triggers))

    if experiment is None:
        from paper_experiment_runner import AgnoMCPExperiment
        experiment = AgnoMCPExperiment(model_profile=model_profile)

    print(f"\n{'='*60}")
    print(f"多轮动态实验：{scenario_id} - {scenario['name']}（最多{max_rounds}轮）")
    print(f"{'='*60}")

    # 静态基线
    print("[Phase 0] 静态基线（无触发）...")
    baseline_mcp = experiment.run_scenario(scenario)
    baseline_outflow = baseline_mcp.get("outflow", scenario["inflow"])
    baseline_eval = _eval_scenario(scenario, baseline_outflow)
    baseline_score = baseline_eval["overall_score"]
    baseline_rate = _dyn_eval.compute_constraint_achievement_rate(baseline_eval)
    print(f"  基线综合评分: {baseline_score:.4f}  约束达成率: {baseline_rate:.4f}")

    rounds_results = []

    for n in range(1, max_rounds + 1):
        print(f"\n[Round {n}] 累积触发前 {n} 个事件...")
        current_scenario = scenario.copy()
        round_tool_calls = baseline_mcp.get("tool_call_count", 0)
        round_adjustments = []
        prev_eval = baseline_eval.copy()
        prev_outflow = baseline_outflow

        for i in range(n):
            trigger = triggers[i]
            print(f"  触发事件 {i+1}: {trigger['description']}")
            adjusted_scenario = _apply_trigger(current_scenario, trigger)
            adj_result = experiment.run_scenario(adjusted_scenario)
            adj_outflow = adj_result.get("outflow", current_scenario["inflow"])
            adj_eval = _eval_scenario(adjusted_scenario, adj_outflow)

            before_rate = _dyn_eval.compute_constraint_achievement_rate(prev_eval)
            after_rate = _dyn_eval.compute_constraint_achievement_rate(adj_eval)
            trend = _dyn_eval.assess_adjustment_effectiveness(before_rate, after_rate)

            round_adjustments.append({
                "trigger_index": i + 1,
                "trigger_type": trigger["type"],
                "outflow_before": prev_outflow,
                "outflow_after": adj_outflow,
                "outflow_delta": round(adj_outflow - prev_outflow, 1),
                "score_before": round(prev_eval["overall_score"], 4),
                "score_after": round(adj_eval["overall_score"], 4),
                "score_delta": round(adj_eval["overall_score"] - prev_eval["overall_score"], 4),
                "constraint_rate_before": round(before_rate, 4),
                "constraint_rate_after": round(after_rate, 4),
                "trend": trend,
            })

            round_tool_calls += adj_result.get("tool_call_count", 0)
            prev_eval = adj_eval
            prev_outflow = adj_outflow
            current_scenario = adjusted_scenario

        final_score = prev_eval["overall_score"]
        final_rate = _dyn_eval.compute_constraint_achievement_rate(prev_eval)

        round_result = {
            "scenario_id": scenario_id,
            "round": n,
            "trigger_count": n,
            "baseline_score": round(baseline_score, 4),
            "final_score": round(final_score, 4),
            "score_improvement": round(final_score - baseline_score, 4),
            "baseline_constraint_rate": round(baseline_rate, 4),
            "final_constraint_rate": round(final_rate, 4),
            "constraint_rate_improvement": round(final_rate - baseline_rate, 4),
            "total_tool_calls": round_tool_calls,
            "adjustments": round_adjustments,
            "final_outflow": prev_outflow,
            "final_violations": prev_eval["constraint_violations"],
        }
        rounds_results.append(round_result)

        print(f"  Round {n} 完成: 最终评分={final_score:.4f} (+{final_score-baseline_score:+.4f}) "
              f"约束达成率={final_rate:.4f} 工具调用={round_tool_calls}")

        if save_result:
            DYNAMIC_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            out_path = DYNAMIC_RESULTS_DIR / f"{scenario_id}_round{n}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(round_result, f, ensure_ascii=False, indent=2)
            print(f"  已保存: {out_path}")

    # 汇总对比表
    comparison_table = [
        {
            "round": r["round"],
            "trigger_count": r["trigger_count"],
            "final_score": r["final_score"],
            "score_improvement": r["score_improvement"],
            "final_constraint_rate": r["final_constraint_rate"],
            "total_tool_calls": r["total_tool_calls"],
        }
        for r in rounds_results
    ]

    summary = {
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "baseline_score": round(baseline_score, 4),
        "baseline_constraint_rate": round(baseline_rate, 4),
        "rounds": {f"round_{r['round']}": r for r in rounds_results},
        "comparison_table": comparison_table,
        "best_round": max(rounds_results, key=lambda r: r["final_score"])["round"] if rounds_results else None,
    }

    if save_result:
        DYNAMIC_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DYNAMIC_RESULTS_DIR / f"{scenario_id}_summary.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"\n场景汇总已保存: {out_path}")

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
    from paper_experiment_runner import AgnoMCPExperiment
    experiment = AgnoMCPExperiment(model_profile=model_profile)
    results = []
    for sid in ids:
        try:
            r = run_static_baseline(sid, experiment=experiment, save_result=True)
            results.append(r)
        except Exception as e:
            print(f"  ✗ {sid} 静态基线失败: {e}")
            results.append({"scenario_id": sid, "error": str(e), "success": False})
    return results


def run_all_multi_round(
    scenario_ids: list[str] | None = None,
    max_rounds: int = 3,
    model_profile: str | None = None,
) -> list[dict]:
    """运行所有场景的多轮动态实验，结果保存到 results/dynamic/。"""
    ids = scenario_ids or ALL_SCENARIO_IDS
    from paper_experiment_runner import AgnoMCPExperiment
    experiment = AgnoMCPExperiment(model_profile=model_profile)
    results = []
    for sid in ids:
        try:
            r = run_multi_round_dynamic_experiment(
                sid, max_rounds=max_rounds, experiment=experiment, save_result=True
            )
            results.append(r)
        except Exception as e:
            print(f"  ✗ {sid} 多轮动态实验失败: {e}")
            results.append({"scenario_id": sid, "error": str(e), "success": False})
    return results


# ============================================================
# 兼容旧接口（供 paper_experiment_runner.run_all 调用）
# ============================================================

def run_dynamic_experiments(
    scenario_ids: list[str] | None = None,
    model_profile: str | None = None,
) -> list[dict]:
    """
    兼容旧接口：运行动态场景实验（单轮，仅触发事件1）。
    新代码请使用 run_all_multi_round。
    """
    ids = scenario_ids or ["S01", "S02", "S03"]
    from paper_experiment_runner import AgnoMCPExperiment
    experiment = AgnoMCPExperiment(model_profile=model_profile)
    results = []
    for sid in ids:
        try:
            summary = run_multi_round_dynamic_experiment(
                sid, max_rounds=1, experiment=experiment, save_result=True
            )
            r1 = summary["rounds"].get("round_1", {})
            adj = r1.get("adjustments", [{}])[0] if r1.get("adjustments") else {}
            results.append({
                "scenario_id": sid,
                "adjustment_effective": r1.get("final_constraint_rate", 0) >= r1.get("baseline_constraint_rate", 0),
                "constraint_achievement_rate": {
                    "before": r1.get("baseline_constraint_rate", 0),
                    "after": r1.get("final_constraint_rate", 0),
                    "trend": adj.get("trend", "maintained"),
                },
                "adjustment_delta": {"outflow_delta": adj.get("outflow_delta", 0)},
                "score_change": r1.get("score_improvement", 0),
            })
        except Exception as e:
            results.append({"scenario_id": sid, "error": str(e)})
    return results


if __name__ == "__main__":
    import sys
    scenario_ids = sys.argv[1:] if len(sys.argv) > 1 else None
    print("=" * 60)
    print("多轮动态实验（所有场景，3轮触发）")
    print("=" * 60)
    results = run_all_multi_round(scenario_ids=scenario_ids, max_rounds=3)
    print(f"\n{'='*60}")
    print(f"实验完成，共 {len(results)} 个场景")
    for r in results:
        if "error" in r:
            print(f"  {r['scenario_id']}: 失败 — {r['error']}")
        else:
            table = r.get("comparison_table", [])
            print(f"  {r['scenario_id']} 基线={r['baseline_score']:.4f}")
            for row in table:
                print(f"    Round{row['round']}({row['trigger_count']}触发): "
                      f"评分={row['final_score']:.4f} ({row['score_improvement']:+.4f}) "
                      f"约束率={row['final_constraint_rate']:.4f} "
                      f"工具调用={row['total_tool_calls']}")
