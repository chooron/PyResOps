"""
MCP Agent 实验框架（agno 框架版本）
对比：人工调度基线 vs 有MCP工具的LLM Agent
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ExperimentResult:
    """单次实验结果"""

    scenario_id: str
    agent_type: str  # "human_baseline", "llm_no_mcp", "llm_with_mcp"
    success: bool
    steps_taken: int
    time_seconds: float
    tool_calls: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    final_answer: str = ""
    rule_compliance_score: float = 0.0  # 0-1, 规则遵守程度
    decision_quality_score: float = 0.0  # 0-1, 决策质量
    notes: str = ""


@dataclass
class ScenarioMetrics:
    """场景级别的汇总指标"""

    scenario_id: str
    human_baseline: Optional[ExperimentResult] = None
    llm_no_mcp_results: List[ExperimentResult] = field(default_factory=list)
    llm_with_mcp_results: List[ExperimentResult] = field(default_factory=list)

    def summary(self) -> dict:
        def avg(results, attr):
            vals = [getattr(r, attr) for r in results if r.success]
            return sum(vals) / len(vals) if vals else 0.0

        return {
            "scenario_id": self.scenario_id,
            "human_baseline": {
                "success": self.human_baseline.success if self.human_baseline else None,
                "steps": self.human_baseline.steps_taken if self.human_baseline else None,
                "time_s": self.human_baseline.time_seconds if self.human_baseline else None,
                "rule_compliance": self.human_baseline.rule_compliance_score
                if self.human_baseline
                else None,
            },
            "llm_no_mcp": {
                "success_rate": sum(r.success for r in self.llm_no_mcp_results)
                / max(len(self.llm_no_mcp_results), 1),
                "avg_steps": avg(self.llm_no_mcp_results, "steps_taken"),
                "avg_time_s": avg(self.llm_no_mcp_results, "time_seconds"),
                "avg_rule_compliance": avg(self.llm_no_mcp_results, "rule_compliance_score"),
                "avg_decision_quality": avg(self.llm_no_mcp_results, "decision_quality_score"),
                "n_trials": len(self.llm_no_mcp_results),
            },
            "llm_with_mcp": {
                "success_rate": sum(r.success for r in self.llm_with_mcp_results)
                / max(len(self.llm_with_mcp_results), 1),
                "avg_steps": avg(self.llm_with_mcp_results, "steps_taken"),
                "avg_time_s": avg(self.llm_with_mcp_results, "time_seconds"),
                "avg_rule_compliance": avg(self.llm_with_mcp_results, "rule_compliance_score"),
                "avg_decision_quality": avg(self.llm_with_mcp_results, "decision_quality_score"),
                "n_trials": len(self.llm_with_mcp_results),
            },
        }


# ============================================================
# 评估维度定义（论文中的评估指标）
# ============================================================

EVALUATION_DIMENSIONS = {
    "task_completion": {
        "name": "任务完成率",
        "description": "是否成功完成调度任务",
        "weight": 0.30,
        "measurement": "binary (0/1)",
    },
    "rule_compliance": {
        "name": "规程遵守率",
        "description": "决策是否符合《水库控制运用计划》规定",
        "weight": 0.25,
        "measurement": "ratio of compliant decisions / total decisions",
    },
    "tool_efficiency": {
        "name": "工具调用效率",
        "description": "完成任务所需的工具调用次数",
        "weight": 0.20,
        "measurement": "steps count (lower is better)",
    },
    "decision_quality": {
        "name": "决策质量",
        "description": "调度方案的水文安全性和经济效益",
        "weight": 0.15,
        "measurement": "expert scoring 0-100",
    },
    "error_recovery": {
        "name": "错误恢复能力",
        "description": "遇到约束违反时的自我纠错能力",
        "weight": 0.10,
        "measurement": "ratio of recovered errors / total errors",
    },
}

# ============================================================
# 实验场景定义
# ============================================================

EXPERIMENT_SCENARIOS = [
    {
        "id": "S01_normal_operation",
        "name": "正常蓄水期调度",
        "description": "汛后蓄水，水位在死水位到正常蓄水位之间",
        "complexity": "low",
        "mcp_tools_required": [
            "get_reservoir_status",
            "calculate_flood_routing",
            "check_safety_constraints",
        ],
    },
    {
        "id": "S02_flood_control",
        "name": "防洪调度",
        "description": "入库流量超过防洪限制水位对应泄量，需紧急防洪操作",
        "complexity": "high",
        "mcp_tools_required": [
            "get_reservoir_status",
            "calculate_flood_routing",
            "check_safety_constraints",
            "get_downstream_impact",
            "query_historical_decisions",
        ],
    },
    {
        "id": "S03_drought_dispatch",
        "name": "抗旱供水调度",
        "description": "枯水期需要保障下游用水，水位接近死水位",
        "complexity": "medium",
        "mcp_tools_required": [
            "get_reservoir_status",
            "calculate_power_generation",
            "check_safety_constraints",
        ],
    },
    {
        "id": "S04_dry_power",
        "name": "枯水期发电优化",
        "description": "枯水期在满足最小下泄流量前提下最大化发电量",
        "complexity": "medium",
        "mcp_tools_required": [
            "get_reservoir_status",
            "calculate_power_generation",
            "calculate_flood_routing",
            "check_safety_constraints",
            "optimize_multi_objective",
        ],
    },
    {
        "id": "S05_multi_objective",
        "name": "多目标联合调度",
        "description": "同时考虑防洪、发电、供水的综合优化",
        "complexity": "very_high",
        "mcp_tools_required": [
            "get_reservoir_status",
            "calculate_flood_routing",
            "check_safety_constraints",
            "calculate_power_generation",
            "query_historical_decisions",
            "optimize_multi_objective",
            "get_downstream_impact",
        ],
    },
]


# ============================================================
# agno Agent 包装器（用于 run_experiments.py 调用）
# ============================================================


class MCPAgentExperiment:
    """
    agno 框架封装的 MCP Agent 实验类。
    供 run_experiments.py 调用，保持接口一致性。
    """

    def __init__(self, model_id: str = "claude-sonnet-4-6"):
        self.model_id = model_id
        self._agent = None

    def _build_agent(self):
        """延迟导入 agno，构建 Agent"""
        from agno.agent import Agent
        from agno.models.anthropic import Claude
        from pyresops.agents import ReservoirPromptPack

        return Agent(
            model=Claude(id=self.model_id),
            tools=[],
            description=ReservoirPromptPack.system_prompt(),
            show_tool_calls=True,
            markdown=False,
        )

    def run_scenario(self, scenario: dict) -> dict:
        """运行单个场景，返回与 run_experiments.py 兼容的结果字典"""
        import re

        start_time = time.time()

        user_message = (
            f"请对以下水库调度场景进行分析并给出调度决策：\n\n"
            f"场景ID: {scenario['id']}\n"
            f"场景名称: {scenario['name']}\n"
            f"场景描述: {scenario['description']}\n\n"
            f"当前状态：\n"
            f"- 入库流量: {scenario['inflow']} m³/s\n"
            f"- 当前水位: {scenario['current_level']} m\n"
            f"- 目标水位: {scenario['target_level']} m\n"
            f"- 季节: {scenario['season']}\n"
            f"- 防洪风险: {scenario['flood_risk']}\n\n"
            f"请使用可用工具进行全面分析，然后给出最终调度方案。"
        )

        try:
            agent = self._build_agent()
            run_response = agent.run(user_message)
            total_time = time.time() - start_time

            final_text = (
                str(run_response.content)
                if hasattr(run_response, "content") and run_response.content
                else ""
            )

            # 提取工具调用信息
            tool_calls_detail: List[dict] = []
            tool_call_count = 0

            if hasattr(run_response, "tools") and run_response.tools:
                for i, tc in enumerate(run_response.tools, 1):
                    tool_name = (
                        tc.get("name", "unknown")
                        if isinstance(tc, dict)
                        else getattr(tc, "name", "unknown")
                    )
                    tool_calls_detail.append({"call_order": i, "tool_name": tool_name})
                tool_call_count = len(tool_calls_detail)

            # 提取出库流量
            outflow = scenario["inflow"]
            for pattern in [
                r"出库流量[：:]\s*(\d+\.?\d*)\s*m³/s",
                r"建议.*?(\d+\.?\d*)\s*m³/s",
                r"泄放\s*(\d+\.?\d*)\s*m³/s",
            ]:
                m = re.search(pattern, final_text)
                if m:
                    outflow = float(m.group(1))
                    break

            return {
                "scenario_id": scenario["id"],
                "method": "agno_mcp_agent",
                "model": self.model_id,
                "outflow": outflow,
                "final_decision_text": final_text,
                "tool_calls": tool_call_count,
                "tool_calls_detail": tool_calls_detail,
                "total_time_seconds": round(total_time, 3),
                "success": True,
            }

        except Exception as e:
            total_time = time.time() - start_time
            return {
                "scenario_id": scenario["id"],
                "method": "agno_mcp_agent",
                "model": self.model_id,
                "outflow": 0,
                "final_decision_text": "",
                "tool_calls": 0,
                "tool_calls_detail": [],
                "total_time_seconds": round(total_time, 3),
                "success": False,
                "error": str(e),
            }


def save_results(results: List[ExperimentResult], filepath: str):
    """保存实验结果到JSON"""
    data = []
    for r in results:
        data.append(
            {
                "scenario_id": r.scenario_id,
                "agent_type": r.agent_type,
                "success": r.success,
                "steps_taken": r.steps_taken,
                "time_seconds": r.time_seconds,
                "tool_calls": r.tool_calls,
                "errors": r.errors,
                "final_answer": r.final_answer,
                "rule_compliance_score": r.rule_compliance_score,
                "decision_quality_score": r.decision_quality_score,
                "notes": r.notes,
            }
        )
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {filepath}")


if __name__ == "__main__":
    print("实验框架初始化完成（agno 版本）")
    print(f"评估维度: {len(EVALUATION_DIMENSIONS)}")
    print(f"实验场景: {len(EXPERIMENT_SCENARIOS)}")
    for s in EXPERIMENT_SCENARIOS:
        print(f"  - {s['id']}: {s['name']} (复杂度: {s['complexity']})")
