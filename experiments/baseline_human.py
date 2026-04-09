"""
基准实验：人工调度流程模拟（使用 pyresops 真实库）

模拟水库调度员按照《水库控制运用计划》手动执行调度决策的过程。
使用 pyresops SimulationEngine 执行真实水量平衡仿真，
EvaluationService 计算真实评分指标。

用于对比 LLM+MCP 自动化调度的能力提升。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class HumanDispatchStep:
    """人工调度步骤记录"""
    step_id: int
    description: str
    manual_lookup_required: bool  # 是否需要查阅文档
    calculation_required: bool    # 是否需要手动计算
    decision_complexity: str      # low / medium / high
    estimated_time_minutes: float
    error_prone: bool             # 是否容易出错


@dataclass
class HumanDispatchSession:
    """一次完整的人工调度会话"""
    scenario_name: str
    steps: List[HumanDispatchStep] = field(default_factory=list)
    total_time_minutes: float = 0.0
    errors_made: int = 0
    documents_consulted: int = 0

    def add_step(self, step: HumanDispatchStep):
        self.steps.append(step)
        self.total_time_minutes += step.estimated_time_minutes
        if step.manual_lookup_required:
            self.documents_consulted += 1

    def simulate_errors(self, seed: Optional[int] = None) -> int:
        """模拟人工操作中的错误率"""
        if seed is not None:
            random.seed(seed)
        errors = 0
        for step in self.steps:
            if step.error_prone:
                error_rates = {"high": 0.15, "medium": 0.05, "low": 0.02}
                rate = error_rates.get(step.decision_complexity, 0.05)
                if random.random() < rate:
                    errors += 1
        self.errors_made = errors
        return errors

    def to_metrics(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "total_steps": len(self.steps),
            "total_time_minutes": self.total_time_minutes,
            "errors_made": self.errors_made,
            "documents_consulted": self.documents_consulted,
            "steps_requiring_calculation": sum(
                1 for s in self.steps if s.calculation_required
            ),
            "high_complexity_steps": sum(
                1 for s in self.steps if s.decision_complexity == "high"
            ),
        }


def build_flood_control_human_session() -> HumanDispatchSession:
    """S02 梅汛期错峰调度场景的人工调度流程"""
    session = HumanDispatchSession(scenario_name="S02_梅汛期错峰调度")
    steps = [
        HumanDispatchStep(1, "接收气象预报，查阅降雨量阈值表",
            True, False, "low", 5.0, False),
        HumanDispatchStep(2, "查阅梅汛期限制水位标准文档（160.0m）",
            True, False, "medium", 8.0, True),
        HumanDispatchStep(3, "测量当前库水位，与汛限水位比对",
            False, True, "medium", 10.0, True),
        HumanDispatchStep(4, "查阅泄洪闸门操作规程",
            True, False, "high", 12.0, True),
        HumanDispatchStep(5, "手动查表估算马斯京根演算参数",
            True, True, "high", 20.0, True),
        HumanDispatchStep(6, "计算区间流量和下游鹤城站预测流量",
            False, True, "high", 25.0, True),
        HumanDispatchStep(7, "确定补偿凑泄量（查表+插值）",
            True, True, "high", 20.0, True),
        HumanDispatchStep(8, "向上级汇报并获取批准",
            False, False, "medium", 30.0, False),
        HumanDispatchStep(9, "执行闸门操作",
            False, False, "low", 10.0, False),
        HumanDispatchStep(10, "记录操作日志",
            False, False, "low", 10.0, False),
        HumanDispatchStep(11, "持续监测水位变化，判断是否需要调整",
            True, True, "high", 60.0, True),
    ]
    for step in steps:
        session.add_step(step)
    return session


def build_dry_power_human_session() -> HumanDispatchSession:
    """S04 枯水期发电优化场景的人工调度流程"""
    session = HumanDispatchSession(scenario_name="S04_枯水期发电优化")
    steps = [
        HumanDispatchStep(1, "查阅当前蓄水量和发电计划",
            True, False, "low", 5.0, False),
        HumanDispatchStep(2, "查阅枯水期最小下泄流量规定（≥50 m³/s）",
            True, False, "medium", 8.0, True),
        HumanDispatchStep(3, "计算可用发电水头",
            False, True, "medium", 10.0, True),
        HumanDispatchStep(4, "查阅机组出力曲线图",
            True, True, "high", 15.0, True),
        HumanDispatchStep(5, "确定最优机组组合方案",
            True, True, "high", 25.0, True),
        HumanDispatchStep(6, "计算日发电量预测",
            False, True, "medium", 15.0, True),
        HumanDispatchStep(7, "与电网调度协商出力计划",
            False, False, "medium", 20.0, False),
        HumanDispatchStep(8, "执行发电调度指令",
            False, False, "low", 5.0, False),
        HumanDispatchStep(9, "记录运行数据",
            False, False, "low", 5.0, False),
    ]
    for step in steps:
        session.add_step(step)
    return session


# ============================================================
# HumanBaselineScheduler — 供 run_experiments.py 调用
# 使用 pyresops SimulationEngine + EvaluationService
# ============================================================

class HumanBaselineScheduler:
    """
    人工调度基线调度器（pyresops 真实库版本）。

    模拟调度员按照《水库控制运用计划》手动执行调度决策的过程。
    决策逻辑基于简化规则（模拟人工判断），但水量平衡仿真和评分
    使用 pyresops 真实引擎（SimulationEngine + EvaluationService）。
    """

    def _build_spec(self, scenario: dict):
        """构建滩坑水电站 ReservoirSpec（使用场景对应汛限水位）."""
        from evaluation_metrics import _build_tankan_spec
        return _build_tankan_spec(
            flood_limit_level=scenario.get("flood_limit_level", 156.5)
        )

    def _human_decide_outflow(self, scenario: dict, spec) -> tuple[float, list[str]]:
        """
        模拟人工调度员根据场景做出出库决策（简化规则）。
        返回 (outflow, steps)。
        """
        inflow        = scenario["inflow"]
        current_level = scenario["current_level"]
        flood_risk    = scenario["flood_risk"]
        _ = scenario["season"]  # 保留字段访问以验证场景完整性
        flood_limit   = spec.flood_limit_level  # noqa: F841

        steps = []
        steps.append("查阅当前水位，与汛限/正常蓄水位比对")
        steps.append("查阅《水库控制运用计划》防洪或发电规程")

        if flood_risk == "extreme":
            # 超标准洪水：全力泄洪（受制于泄洪能力）
            steps.append("启动应急预案：全力开启溢洪道")
            steps.append("向上级汇报，发布下游预警")
            max_discharge = spec.discharge_capacity.get_max_discharge(current_level)
            outflow = min(inflow * 1.1, max_discharge)
        elif flood_risk == "high":
            # 防洪：入库×1.05，但不超泄洪能力
            steps.append("计算需要泄放的流量（查泄洪曲线）")
            steps.append("确定溢洪道开度，向上级汇报")
            steps.append("执行泄洪操作，记录日志")
            max_discharge = spec.discharge_capacity.get_max_discharge(current_level)
            outflow = min(inflow * 1.05, max_discharge)
        elif flood_risk == "medium":
            steps.append("计算适度控泄方案（预泄至汛限）")
            steps.append("执行调度指令，监测水位")
            outflow = max(inflow * 1.2, 1500.0)  # 预泄加大出库
        elif flood_risk == "low":
            steps.append("制定蓄水计划，平衡发电与供水")
            steps.append("执行调度，记录运行数据")
            outflow = max(inflow * 0.85, spec.dead_level)
        else:  # none（枯水/发电）
            steps.append("计算发电优化方案（查机组出力曲线）")
            steps.append("与电网协商出力计划，执行发电指令")
            outflow = max(inflow * 0.9, 50.0)  # 枯水期适量控泄

        # 约束修正（模拟人工可能忽略的边界）
        outflow = max(outflow, 50.0)   # 生态流量下限
        max_discharge = spec.discharge_capacity.get_max_discharge(current_level)
        outflow = min(outflow, max_discharge)

        return round(outflow, 1), steps

    def schedule(self, scenario: dict) -> dict:
        """
        根据场景参数模拟人工调度决策，使用 pyresops 执行仿真和评估。
        """
        from pyresops.core import SimulationEngine
        from pyresops.domain.constraint import Constraint, ConstraintSet
        from pyresops.domain.forecast import ForecastBundle, ForecastSeries
        from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
        from pyresops.domain.reservoir import ReservoirState
        from pyresops.modules import ConstantReleaseModule
        from pyresops.services import EvaluationService

        spec = self._build_spec(scenario)
        outflow, steps = self._human_decide_outflow(scenario, spec)

        # ── 使用 pyresops 仿真引擎执行水量平衡 ────────────────────
        start = datetime(2025, 6, 1, 0, 0, 0)
        step_seconds = scenario.get("time_step_hours", 3) * 3600
        n_steps = scenario.get("duration_hours", 48) // scenario.get("time_step_hours", 3)
        end = start + timedelta(hours=scenario.get("duration_hours", 48))

        state = ReservoirState(
            timestamp=start,
            level=scenario["current_level"],
            storage=scenario["initial_storage"],
            inflow=scenario["initial_inflow"],
            outflow=scenario["initial_inflow"],
        )

        timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
        forecast = ForecastBundle(
            forecast_time=start,
            series=[ForecastSeries(
                variable="inflow",
                timestamps=timestamps,
                values=[float(scenario["inflow"])] * n_steps,
                unit="m³/s",
            )],
        )

        horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)
        program = DispatchProgram(
            id=f"{scenario['id']}_human",
            name=f"{scenario['name']} 人工调度",
            time_horizon=horizon,
            module_sequence=[
                ModuleInstance(
                    id="m01",
                    module_type="constant_release",
                    parameters={"target_flow": outflow},
                )
            ],
        )

        modules_map = {"constant_release": ConstantReleaseModule({"target_flow": outflow})}
        engine = SimulationEngine(spec)
        sim_result = engine.simulate(program, state, forecast, modules_map)

        # ── 使用 EvaluationService 评估 ────────────────────────────
        constraint_set = ConstraintSet(constraints=[
            Constraint(
                id="level_min",
                name="死水位下限",
                constraint_type="level_min",
                parameters={"min_level": spec.dead_level},
                priority=10,
            ),
            Constraint(
                id="level_max",
                name="正常蓄水位上限",
                constraint_type="level_max",
                parameters={"max_level": spec.normal_level},
                priority=10,
            ),
            Constraint(
                id="eco_flow",
                name="生态最小流量",
                constraint_type="ecological_min_flow",
                parameters={"min_flow": 50.0},
                priority=9,
            ),
        ])

        ev = EvaluationService(spec)
        eval_result = ev.evaluate(sim_result, constraint_set=constraint_set)

        # ── 约束违反检查 ──────────────────────────────────────────
        violations = []
        if scenario.get("flood_risk") in ("high", "extreme") and outflow < scenario["inflow"]:
            violations.append("防洪高风险时出库小于入库")
        if outflow < 50.0:
            violations.append("出库低于最小生态流量50 m³/s")

        return {
            "outflow": outflow,
            "decision": f"人工调度决策：出库流量 {outflow} m³/s",
            "steps": steps,
            "step_count": len(steps),
            "safety_score": round(eval_result.flood_control_score, 3),
            "benefit_score": round(
                (eval_result.power_generation_score + eval_result.water_supply_score) / 2, 3
            ),
            "overall_score": round(eval_result.overall_score, 3),
            "decision_quality": round(eval_result.overall_score, 3),
            "violations": violations,
            "constraint_violations": len(eval_result.constraint_violations),
            "sim_max_level": round(sim_result.max_level, 3),
            "sim_min_level": round(sim_result.min_level, 3),
            "sim_final_level": round(sim_result.snapshots[-1].level, 3),
            "method": "human_baseline",
        }


class StaticBaselineReport:
    """生成静态场景5维评分对比表（LLM vs 人工基线）。

    供 static_experiment.py 调用，输出论文表格所需格式。
    """

    SCORE_DIMS = ["overall", "flood_control", "power", "water_supply", "ecological", "compliance"]

    def generate_comparison_table(
        self, llm_scores: dict, human_scores: dict
    ) -> dict:
        """生成5维评分对比字典。

        Args:
            llm_scores:   LLM 调度5维评分字典
            human_scores: 人工基线5维评分字典

        Returns:
            包含每个维度 llm/human/diff 三列的对比字典
        """
        table = {}
        for dim in self.SCORE_DIMS:
            llm_val = llm_scores.get(dim, 0.0)
            human_val = human_scores.get(dim, 0.0)
            table[dim] = {
                "llm": round(llm_val, 4),
                "human": round(human_val, 4),
                "diff": round(llm_val - human_val, 4),
                "llm_better": llm_val >= human_val,
            }
        return table


def run_baseline_experiment(n_trials: int = 30) -> list[dict]:
    """
    运行基准实验，模拟 n_trials 次人工调度会话。
    返回所有实验的度量数据列表。

    注：此函数保留供兼容性使用。原速度/错误率统计逻辑（基于旧命题）
    已不再作为论文核心指标，请使用 HumanBaselineScheduler.schedule() 获取
    基于 pyresops 真实评估的5维评分基线。
    """
    results = []
    sessions_builders = [
        build_flood_control_human_session,
        build_dry_power_human_session,
    ]
    for trial in range(n_trials):
        for builder in sessions_builders:
            session = builder()
            session.simulate_errors(seed=trial)
            metrics = session.to_metrics()
            metrics["trial_id"] = trial
            results.append(metrics)
    return results


if __name__ == "__main__":
    results = run_baseline_experiment(n_trials=30)

    from collections import defaultdict
    import statistics

    by_scenario = defaultdict(list)
    for r in results:
        by_scenario[r["scenario"]].append(r)

    print("=" * 60)
    print("人工调度基准实验结果")
    print("=" * 60)

    for scenario, records in by_scenario.items():
        times = [r["total_time_minutes"] for r in records]
        errors = [r["errors_made"] for r in records]
        print(f"\n场景: {scenario}")
        print(f"  调度步骤数: {records[0]['total_steps']}")
        print(f"  平均耗时: {statistics.mean(times):.1f} 分钟")
        print(f"  平均错误数: {statistics.mean(errors):.2f}")
        print(f"  错误率: {statistics.mean(errors)/records[0]['total_steps']*100:.1f}%")
        print(f"  需查阅文档步骤数: {records[0]['documents_consulted']}")
        print(f"  需计算步骤数: {records[0]['steps_requiring_calculation']}")
        print(f"  高复杂度步骤数: {records[0]['high_complexity_steps']}")
