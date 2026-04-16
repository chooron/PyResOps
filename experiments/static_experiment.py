"""
静态场景实验模块

负责 S04（枯水期发电优化）和 S05（梅台过渡期）静态场景的完整实验流程。

核心功能：
- 执行 LLM 完整调度流程（工具调用链）
- 调用 evaluation_metrics.py 获取约束违反数 + 5维评分
- 与 baseline_human.py 静态基线做综合评分对比
- 输出结果到 results/static/{scenario_id}.json
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from experiments.baseline_human import HumanBaselineScheduler
from experiments.evaluation_metrics import _build_tankan_spec, _run_pyresops_eval

# 静态场景定义
STATIC_SCENARIOS = [
    {
        "id": "S04",
        "name": "枯水期发电优化",
        "description": "枯水期在满足最小下泄流量前提下最大化发电量",
        "flood_limit_level": 156.5,
        "current_level": 150.0,
        "initial_storage": 28.72,
        "initial_inflow": 80.0,
        "season": "dry",
        "flood_risk": "none",
        "inflow": 70.0,
        "target_level": 145.0,
        "duration_hours": 24 * 30,
        "time_step_hours": 24,
    },
    {
        "id": "S05",
        "name": "梅台过渡期降水位",
        "description": "梅汛期向台汛期过渡，水位从160m降至156.5m",
        "flood_limit_level": 156.5,
        "current_level": 160.0,
        "initial_storage": 35.20,
        "initial_inflow": 500.0,
        "season": "transition",
        "flood_risk": "low",
        "inflow": 500.0,
        "target_level": 156.5,
        "duration_hours": 72,
        "time_step_hours": 3,
    },
]


def _get_results_dir() -> Path:
    """获取结果输出目录（experiments/results/static/）"""
    here = Path(__file__).parent
    results_dir = here / "results" / "static"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def _derive_tool_calls_detail(result: dict) -> list[dict]:
    existing = result.get("tool_calls_detail")
    if isinstance(existing, list) and existing:
        normalized = []
        for idx, item in enumerate(existing, 1):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "call_order": int(item.get("call_order", idx)),
                    "tool_name": str(item.get("tool_name", "unknown")),
                }
            )
        if normalized:
            return normalized

    trace = result.get("llm_execution_trace", {})
    events = trace.get("tool_events", []) if isinstance(trace, dict) else []
    if isinstance(events, list) and events:
        normalized = []
        for idx, event in enumerate(events, 1):
            if not isinstance(event, dict):
                continue
            normalized.append(
                {
                    "call_order": int(event.get("call_order", idx)),
                    "tool_name": str(event.get("tool_name", "unknown")),
                }
            )
        if normalized:
            return normalized

    chain = result.get("tool_call_chain", [])
    if isinstance(chain, list):
        return [
            {
                "call_order": idx,
                "tool_name": str(name),
            }
            for idx, name in enumerate(chain, 1)
        ]

    return []


def run_llm_scenario(scenario: dict, model_profile: str | None = None) -> dict:
    """
    使用 LLM + MCP 工具链运行单个静态场景。

    Args:
        scenario: 场景参数字典
        model_profile: 模型配置名称（对应 experiments/config/llm_config.yml 中的 profile）

    Returns:
        包含工具调用链、评分、约束检查等完整信息的字典
    """
    from pyresops.agents import ReservoirAgentRuntime

    exp = ReservoirAgentRuntime(model_profile=model_profile)
    start_time = time.time()
    mcp_result = exp.run_scenario(scenario)
    elapsed = time.time() - start_time

    outflow = mcp_result.get("outflow", scenario["inflow"])
    spec = _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))
    eval_dict = _run_pyresops_eval(scenario, outflow, spec)

    tool_call_chain = _derive_tool_calls_detail(mcp_result)
    tool_names = [tc.get("tool_name", "unknown") for tc in tool_call_chain]

    # 流程完整性判断（是否调用了核心5个工具）
    required_tools = {
        "get_reservoir_status",
        "simulate_dispatch_program",
        "evaluate_dispatch_result",
    }
    process_complete = required_tools.issubset(set(tool_names))

    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "method": "llm_mcp_agent",
        "model": mcp_result.get("model", "unknown"),
        "outflow": outflow,
        "llm_constraint_violations": eval_dict["constraint_violations"],
        "llm_scores": {
            "overall": eval_dict["overall_score"],
            "flood_control": eval_dict["flood_control_score"],
            "power": eval_dict["power_generation_score"],
            "water_supply": eval_dict["water_supply_score"],
            "ecological": eval_dict["ecological_score"],
            "compliance": 1.0 if eval_dict["constraint_violations"] == 0 else 0.0,
        },
        "tool_call_chain": tool_names,
        "tool_call_count": len(tool_names),
        "process_complete": process_complete,
        "total_time_seconds": round(elapsed, 3),
        "final_decision_text": mcp_result.get("final_decision_text", ""),
        "success": mcp_result.get("success", False),
        "sim_details": {k: v for k, v in eval_dict.items() if k.startswith("sim_")},
    }


def run_human_scenario(scenario: dict) -> dict:
    """
    运行人工基线调度场景。

    Args:
        scenario: 场景参数字典

    Returns:
        人工调度结果字典（含5维评分）
    """
    scheduler = HumanBaselineScheduler()
    result = scheduler.schedule(scenario)

    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "method": "human_baseline",
        "outflow": result["outflow"],
        "human_constraint_violations": result["constraint_violations"],
        "human_scores": {
            "overall": result["overall_score"],
            "flood_control": result["safety_score"],
            "power": result.get("benefit_score", 0.0),
            "water_supply": result.get("benefit_score", 0.0),
            "ecological": result.get("eco_score", result["overall_score"]),
            "compliance": 1.0 if result["constraint_violations"] == 0 else 0.0,
        },
        "steps": result.get("steps", []),
        "step_count": result.get("step_count", 0),
        "violations": result.get("violations", []),
    }


def run_static_experiment(scenario: dict, model_profile: str | None = None) -> dict:
    """
    运行单个静态场景完整实验（LLM + 人工基线对比）。

    Args:
        scenario: 场景参数字典
        model_profile: 模型配置名称

    Returns:
        完整结果字典，包含 LLM 结果、人工基线结果、对比分析
    """
    print(f"\n[静态实验] 场景 {scenario['id']}: {scenario['name']}")
    print(f"  入库流量: {scenario['inflow']} m³/s, 当前水位: {scenario['current_level']} m")

    # 1. 运行人工基线
    print("  → 运行人工基线...")
    human_result = run_human_scenario(scenario)

    # 2. 运行 LLM 调度
    print("  → 运行 LLM 调度...")
    llm_result = run_llm_scenario(scenario, model_profile=model_profile)

    # 3. 综合对比
    h_scores = human_result["human_scores"]
    l_scores = llm_result["llm_scores"]

    def score_diff(key: str) -> float:
        return round(l_scores.get(key, 0) - h_scores.get(key, 0), 4)

    comparison = {
        "overall_diff": score_diff("overall"),
        "flood_control_diff": score_diff("flood_control"),
        "power_diff": score_diff("power"),
        "water_supply_diff": score_diff("water_supply"),
        "ecological_diff": score_diff("ecological"),
        "compliance_diff": score_diff("compliance"),
        "violation_delta": (
            llm_result["llm_constraint_violations"] - human_result["human_constraint_violations"]
        ),
        "llm_better": l_scores["overall"] >= h_scores["overall"],
    }

    result = {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "experiment_time": datetime.now().isoformat(),
        "llm_result": llm_result,
        "human_result": human_result,
        "comparison": comparison,
        # 顶层快速访问字段（重构计划要求）
        "llm_constraint_violations": llm_result["llm_constraint_violations"],
        "llm_scores": l_scores,
        "human_scores": h_scores,
        "tool_call_chain": llm_result["tool_call_chain"],
        "process_complete": llm_result["process_complete"],
    }

    # 4. 保存到文件
    out_path = _get_results_dir() / f"{scenario['id']}_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 结果已保存: {out_path}")

    return result


def run_static_experiments(
    scenario_ids: list[str] | None = None,
    model_profile: str | None = None,
) -> list[dict]:
    """
    运行所有静态场景实验（S04, S05）。

    Args:
        scenario_ids: 要运行的场景ID列表，None 表示运行所有静态场景
        model_profile: 模型配置名称

    Returns:
        所有场景结果列表
    """
    if scenario_ids is None:
        scenarios = STATIC_SCENARIOS
    else:
        scenarios = [s for s in STATIC_SCENARIOS if s["id"] in scenario_ids]

    results = []
    for scenario in scenarios:
        try:
            result = run_static_experiment(scenario, model_profile=model_profile)
            results.append(result)
        except Exception as e:
            print(f"  ✗ 场景 {scenario['id']} 失败: {e}")
            results.append(
                {
                    "scenario_id": scenario["id"],
                    "error": str(e),
                    "success": False,
                }
            )

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("静态场景实验（S04、S05）")
    print("=" * 60)
    results = run_static_experiments()

    print("\n" + "=" * 60)
    print("实验汇总")
    print("=" * 60)
    for r in results:
        if "error" in r:
            print(f"  {r['scenario_id']}: 失败 — {r['error']}")
        else:
            llm = r["llm_scores"]["overall"]
            human = r["human_scores"]["overall"]
            diff = r["comparison"]["overall_diff"]
            viol = r["llm_constraint_violations"]
            complete = "✓" if r["process_complete"] else "✗"
            print(
                f"  {r['scenario_id']}: LLM综合={llm:.4f} | 人工基线={human:.4f} | "
                f"差值={diff:+.4f} | 约束违反={viol} | 流程完整={complete}"
            )
