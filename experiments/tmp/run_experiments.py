"""
实验运行主脚本（agno 框架 + pyresops 真实库版本）
对比：人工调度基线 vs agno MCP 大模型调度的性能

用法:
    python experiments/run_experiments.py                    # 使用 config.yml 中 default_profile
    python experiments/run_experiments.py --model deepseek   # 使用 deepseek 配置
    python experiments/run_experiments.py --model qwen       # 使用 qwen 配置
    python experiments/run_experiments.py --model minimax    # 使用 minimax 配置
    python experiments/run_experiments.py --model opencode_minmax_25  # 使用 OpenCode + MiniMax 2.5 配置
    python experiments/run_experiments.py --model claude     # 使用 claude 配置
    python experiments/run_experiments.py --model openai     # 使用 openai 配置

    # 论文实验（静态基线 + 多轮动态对比）
    python experiments/run_experiments.py --paper
    python experiments/run_experiments.py --paper --model deepseek
"""

import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.baseline_human import HumanBaselineScheduler
from experiments.scenario_config import get_scenarios
from pyresops.agents import ReservoirAgentRuntime
from experiments.evaluation_metrics import ExperimentEvaluator


SCENARIOS = list(get_scenarios().values())


def run_full_experiment(model_profile: str | None = None):
    """运行完整对比实验：人工基线 vs agno MCP Agent（均使用 pyresops 真实库）"""
    print("=" * 60)
    print("水库调度 MCP 大模型能力评估实验（agno + pyresops 真实库版本）")
    print("=" * 60)
    print(f"实验时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"实验场景: {len(SCENARIOS)} 个（滩坑水电站 S01~S05）")
    print(f"模型配置: {model_profile or '默认（config.yml default_profile）'}")

    results = []
    evaluator = ExperimentEvaluator()
    human_scheduler = HumanBaselineScheduler()
    mcp_experiment = ReservoirAgentRuntime(model_profile=model_profile)

    for scenario in SCENARIOS:
        print(f"\n{'=' * 50}")
        print(f"场景 {scenario['id']}: {scenario['name']}")
        print(f"描述: {scenario['description']}")
        print(f"入库流量: {scenario['inflow']} m³/s")
        print(f"当前水位: {scenario['current_level']} m")
        print(f"汛限水位: {scenario['flood_limit_level']} m")
        print(f"防洪风险: {scenario['flood_risk']}")

        # ── 1. 人工调度基线（使用 pyresops 仿真 + 评估）────────────────
        print("\n[人工调度基线]")
        t0 = time.time()
        try:
            human_result = human_scheduler.schedule(scenario)
            human_time = time.time() - t0
            human_result["decision_time"] = human_time
            human_result["scenario_id"] = scenario["id"]
            print(f"  决策时间: {human_time:.3f}s")
            print(f"  出库流量: {human_result.get('outflow', 'N/A')} m³/s")
            print(f"  综合评分: {human_result.get('overall_score', 'N/A')}")
            print(f"  防洪评分: {human_result.get('safety_score', 'N/A')}")
            print(f"  末水位:   {human_result.get('sim_final_level', 'N/A')} m")
        except Exception as e:
            print(f"  ✗ 人工基线失败: {e}")
            human_result = {
                "decision_time": 0,
                "method": "human_baseline",
                "scenario_id": scenario["id"],
                "outflow": scenario["inflow"],
                "overall_score": 0,
                "safety_score": 0,
                "benefit_score": 0,
                "error": str(e),
            }

        # ── 2. agno MCP 大模型调度（使用 pyresops @tool 工具）──────────
        print("\n[agno MCP 大模型调度]")
        t1 = time.time()
        try:
            mcp_result = mcp_experiment.run_scenario(scenario)
            mcp_time = time.time() - t1
            mcp_result["decision_time"] = mcp_time
            mcp_result["scenario_id"] = scenario["id"]
            print(f"  决策时间: {mcp_time:.3f}s")
            print(f"  工具调用次数: {mcp_result.get('tool_call_count', 0)}")
            print(f"  出库流量: {mcp_result.get('outflow', 'N/A')} m³/s")
            print(f"  成功: {mcp_result.get('success', False)}")
        except Exception as e:
            mcp_time = time.time() - t1
            print(f"  ✗ MCP 实验失败: {e}")
            mcp_result = {
                "decision_time": mcp_time,
                "method": "agno_mcp_agent",
                "scenario_id": scenario["id"],
                "tool_call_count": 0,
                "outflow": 0,
                "success": False,
                "error": str(e),
            }

        # ── 3. 使用 pyresops EvaluationService 对比评估 ────────────────
        print("\n[对比评估（pyresops EvaluationService）]")
        try:
            evaluation = evaluator.compare(human_result, mcp_result, scenario)
            print(
                f"  综合得分 - 人工: {evaluation['human_overall']:.4f} | MCP: {evaluation['mcp_overall']:.4f}"
            )
            print(
                f"  防洪评分 - 人工: {evaluation['human_safety']:.4f} | MCP: {evaluation['mcp_safety']:.4f}"
            )
            print(
                f"  生态评分 - 人工: {evaluation['human_eco_score']:.4f} | MCP: {evaluation['mcp_eco_score']:.4f}"
            )
            print(
                f"  约束违反 - 人工: {evaluation['human_violations']} | MCP: {evaluation['mcp_violations']}"
            )
        except Exception as e:
            print(f"  ✗ 评估失败: {e}")
            evaluation = {"error": str(e)}

        results.append(
            {
                "scenario": scenario,
                "human": human_result,
                "mcp": mcp_result,
                "evaluation": evaluation,
            }
        )

    # ── 汇总统计 ────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("实验汇总统计")
    print("=" * 60)

    try:
        summary = evaluator.summarize(results)

        print(f"场景总数: {summary['total_scenarios']}")

        print("\n人工调度平均指标:")
        print(f"  平均综合得分: {summary['human_avg_overall']:.4f}")
        print(f"  平均防洪评分: {summary['human_avg_safety']:.4f}")
        print(f"  平均效益评分: {summary['human_avg_benefit']:.4f}")
        print(f"  平均生态评分: {summary['human_avg_eco']:.4f}")
        print(f"  平均决策时间: {summary['human_avg_time']:.3f}s")
        print(f"  平均约束违反: {summary['human_avg_violations']:.2f}")

        print("\nagno MCP 大模型平均指标:")
        print(f"  平均综合得分: {summary['mcp_avg_overall']:.4f}")
        print(f"  平均防洪评分: {summary['mcp_avg_safety']:.4f}")
        print(f"  平均效益评分: {summary['mcp_avg_benefit']:.4f}")
        print(f"  平均生态评分: {summary['mcp_avg_eco']:.4f}")
        print(f"  平均决策时间: {summary['mcp_avg_time']:.3f}s")
        print(f"  平均工具调用: {summary['mcp_avg_tool_calls']:.1f}次")
        print(f"  平均约束违反: {summary['mcp_avg_violations']:.2f}")

        print("\nMCP 相对人工的提升（基于 pyresops EvaluationService）:")
        print(f"  综合得分提升: {summary['overall_improvement']:+.2f}%")
        print(f"  防洪评分提升: {summary['safety_improvement']:+.2f}%")
        print(f"  效益评分提升: {summary['benefit_improvement']:+.2f}%")
        print(f"  生态评分提升: {summary['eco_improvement']:+.2f}%")
        print(f"  约束违反变化: {summary['violations_delta']:+.4f}（负数=改善）")

    except Exception as e:
        summary = {"error": str(e)}
        print(f"汇总统计失败: {e}")

    # ── 保存结果 ────────────────────────────────────────────────────────
    output_path = Path(__file__).parent / "results"
    output_path.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = output_path / f"experiment_results_{timestamp}.json"
    summary_file = output_path / f"summary_{timestamp}.json"

    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✓ 结果已保存至: {output_path}")
    print(f"  详细结果: {results_file.name}")
    print(f"  汇总统计: {summary_file.name}")

    return results, summary


def run_paper_experiments(model_profile: str | None = None) -> dict:
    """
    论文实验入口：静态基线 + 阶段式动态对比（5场景 × 4阶段）。

    结果目录：
      experiments/results/static/   — 无触发基线（5个文件）
      experiments/results/dynamic/  — 阶段触发结果（5场景 × 4阶段 + 5个汇总）
      experiments/results/paper_summary_{ts}.json — 论文用汇总对比表
    """
    from experiments.dynamic_experiment import run_all_static_baselines, run_all_multi_round

    print("=" * 60)
    print("PyResOps 论文实验（静态基线 + 阶段式动态对比）")
    print("=" * 60)
    print(f"实验时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模型配置: {model_profile or '默认（config.yml default_profile）'}")
    print("场景: S01~S05，每场景 4 个动态阶段（T0~T3）")

    print("\n[Step 1/2] 运行静态基线（无触发）...")
    static_results = run_all_static_baselines(model_profile=model_profile)

    print("\n[Step 2/2] 运行阶段式动态实验（4阶段触发）...")
    dynamic_results = run_all_multi_round(max_rounds=4, model_profile=model_profile)

    # 生成论文汇总对比表
    paper_table = []
    dynamic_map = {
        r["scenario_id"]: r for r in dynamic_results if "scenario_id" in r and "error" not in r
    }
    static_map = {
        r["scenario_id"]: r for r in static_results if "scenario_id" in r and "error" not in r
    }

    for sid in ["S01", "S02", "S03", "S04", "S05"]:
        static = static_map.get(sid, {})
        dynamic = dynamic_map.get(sid, {})
        row = {
            "scenario_id": sid,
            "static_score": static.get("scores", {}).get("overall", None),
            "static_constraint_rate": static.get("constraint_achievement_rate", None),
            "dynamic_overall_pass_rate": dynamic.get("overall_pass_rate", None),
            "dynamic_stage_pass_count": dynamic.get("stage_pass_count", None),
            "dynamic_stage_total": dynamic.get("stage_total", None),
        }
        stages = dynamic.get("stages", [])
        for index in range(4):
            stage = stages[index] if index < len(stages) else {}
            row[f"stage{index}_pass"] = stage.get("compliance", {}).get("pass")
            row[f"stage{index}_outflow"] = stage.get("llm_outflow")
            row[f"stage{index}_level_before"] = stage.get("state_before", {}).get("level")
        paper_table.append(row)

    summary = {
        "experiment_time": datetime.now().isoformat(),
        "model_profile": model_profile or "default",
        "paper_table": paper_table,
        "static_results": static_results,
        "dynamic_results": dynamic_results,
    }

    output_path = Path(__file__).parent / "results"
    output_path.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = output_path / f"paper_summary_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n论文汇总已保存: {out_file}")

    # 打印对比表
    print("\n" + "=" * 60)
    print("论文对比表（静态基线 vs 阶段式动态）")
    print("=" * 60)
    header = f"{'场景':<6} {'静态基线':>8} {'通过率':>8} {'通过数':>8}"
    print(header)
    print("-" * len(header))
    for row in paper_table:
        s = row.get("static_score")

        def fmt(value):
            return f"{value:.4f}" if value is not None else "  N/A  "

        pass_rate = row.get("dynamic_overall_pass_rate")
        pass_ratio = row.get("dynamic_stage_pass_count")
        pass_total = row.get("dynamic_stage_total")
        pass_text = (
            f"{pass_ratio}/{pass_total}"
            if pass_ratio is not None and pass_total is not None
            else "N/A"
        )
        print(f"{row['scenario_id']:<6} {fmt(s):>8} {fmt(pass_rate):>8} {pass_text:>8}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PyResOps 实验运行器")
    parser.add_argument("--model", type=str, default=None, help="模型配置名称")
    parser.add_argument("--paper", action="store_true", help="运行论文实验（静态+多轮动态）")
    args = parser.parse_args()

    if args.paper:
        run_paper_experiments(model_profile=args.model)
    else:
        run_full_experiment(model_profile=args.model)
