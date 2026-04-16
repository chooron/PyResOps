"""
评估指标模块（pyresops 真实库版本）

使用 pyresops EvaluationService 计算真实评估指标，
对比人工调度与 MCP 智能体调度的性能差异。

论文核心指标：
1. 综合评分 (Overall Score) — EvaluationService 输出
2. 防洪评分 (Flood Control Score)
3. 供水评分 (Water Supply Score)
4. 发电评分 (Power Generation Score)
5. 生态评分 (Ecological Score)
6. 约束违反数 (Constraint Violations)
7. 决策时间 (Decision Time)
8. 工具调用次数 (Tool Call Count, MCP专有)
"""

from __future__ import annotations

from datetime import timedelta

from pyresops.core import SimulationEngine
from pyresops.core import resolve_scenario_start_time
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
from pyresops.domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
    ReservoirState,
)
from pyresops.modules import ConstantReleaseModule
from pyresops.services import EvaluationService


def _build_tankan_spec(flood_limit_level: float = 156.5) -> ReservoirSpec:
    """构建滩坑水电站规格."""
    levels = [120.0, 130.0, 140.0, 150.0, 156.5, 160.0, 161.5, 165.87, 169.15]
    storages = [13.94, 18.14, 23.05, 28.72, 32.51, 35.20, 36.17, 39.37, 41.90]
    d_levels = [148.0, 150.0, 155.0, 160.0, 161.5, 165.87]
    d_discharges = [0.0, 361.0, 2456.0, 5861.0, 6649.0, 11085.0]
    return ReservoirSpec(
        id="tankan_2025",
        name="滩坑水电站",
        dead_level=120.0,
        normal_level=160.0,
        flood_limit_level=flood_limit_level,
        design_flood_level=165.87,
        check_flood_level=169.15,
        total_capacity=41.90,
        flood_capacity=3.50,
        level_storage_curve=LevelStorageCurve(levels=levels, storages=storages),
        discharge_capacity=DischargeCapacity(levels=d_levels, max_discharges=d_discharges),
    )


def _run_pyresops_eval(
    scenario: dict,
    outflow: float,
    spec: ReservoirSpec,
) -> dict:
    """
    使用 pyresops 引擎对给定出库流量方案做水量平衡仿真 + 效益评估。

    Returns:
        包含 overall_score、flood_control_score、water_supply_score、
        power_generation_score、ecological_score、constraint_violations 的字典
    """
    start = resolve_scenario_start_time(scenario)
    step_seconds = scenario["time_step_hours"] * 3600
    n_steps = scenario["duration_hours"] // scenario["time_step_hours"]
    end = start + timedelta(hours=scenario["duration_hours"])

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
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=timestamps,
                values=[float(scenario["inflow"])] * n_steps,
                unit="m³/s",
            )
        ],
    )

    horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)
    program = DispatchProgram(
        id=f"{scenario['id']}_eval",
        name=f"{scenario['name']} 评估",
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

    # 构建评估约束集
    constraint_set = ConstraintSet(
        constraints=[
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
                constraint_type="flow_min",
                parameters={"min_flow": 50.0},
                priority=9,
            ),
        ]
    )

    ev = EvaluationService(spec)
    eval_result = ev.evaluate(sim_result, constraint_set=constraint_set)

    return {
        "overall_score": round(eval_result.overall_score, 4),
        "flood_control_score": round(eval_result.flood_control_score, 4),
        "water_supply_score": round(eval_result.water_supply_score, 4),
        "power_generation_score": round(eval_result.power_generation_score, 4),
        "ecological_score": round(eval_result.ecological_score, 4),
        "constraint_violations": len(eval_result.constraint_violations),
        "sim_max_level": round(sim_result.max_level, 3),
        "sim_min_level": round(sim_result.min_level, 3),
        "sim_final_level": round(sim_result.snapshots[-1].level, 3)
        if sim_result.snapshots
        else None,
        "sim_avg_outflow": round(sim_result.avg_outflow, 1),
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _partial_credit(actual: float, target: float, worst_case: float) -> float:
    denominator = abs(worst_case - target)
    if denominator <= 1e-9:
        return 1.0 if abs(actual - target) <= 1e-9 else 0.0
    return round(_clamp(1.0 - abs(actual - target) / denominator), 4)


def _evaluate_pass_condition(
    condition: dict,
    llm_outflow: float,
    state_before: dict,
    state_after_sim: dict,
) -> dict:
    condition_type = condition["type"]

    if condition_type == "level_target":
        target = float(condition["target"])
        tolerance = float(condition.get("tolerance", 0.0))
        actual = float(state_after_sim["level"])
        before_level = float(state_before["level"])
        before_gap = abs(before_level - target)
        after_gap = abs(actual - target)
        return {
            "pass": after_gap <= tolerance,
            "constraint_violations": 0 if after_gap <= tolerance else 1,
            "response_direction_correct": after_gap <= before_gap,
            "partial_credit": _partial_credit(actual, target, before_level),
            "detail": (
                f"level_target: actual={actual:.3f}, target={target:.3f}, tolerance={tolerance:.3f}"
            ),
        }

    if condition_type == "level_max":
        max_level = float(condition["max_level"])
        actual = float(state_after_sim["level"])
        before_level = float(state_before["level"])
        return {
            "pass": actual <= max_level,
            "constraint_violations": 0 if actual <= max_level else 1,
            "response_direction_correct": actual <= before_level or actual <= max_level,
            "partial_credit": 1.0
            if actual <= max_level
            else _partial_credit(actual, max_level, before_level),
            "detail": f"level_max: actual={actual:.3f}, max={max_level:.3f}",
        }

    if condition_type == "flow_limit":
        max_flow = float(condition["max_flow"])
        actual = float(llm_outflow)
        return {
            "pass": actual <= max_flow,
            "constraint_violations": 0 if actual <= max_flow else 1,
            "response_direction_correct": actual <= max_flow,
            "partial_credit": 1.0
            if actual <= max_flow
            else _partial_credit(actual, max_flow, max_flow * 2.0),
            "detail": f"flow_limit: actual={actual:.1f}, max={max_flow:.1f}",
        }

    if condition_type == "direction":
        expected = condition["expected"]
        previous_outflow = float(state_before.get("outflow", state_before.get("inflow", 0.0)))
        current_outflow = float(llm_outflow)
        epsilon = float(condition.get("epsilon", 1e-6))

        if expected == "increase":
            passed = current_outflow > previous_outflow + epsilon
        elif expected == "decrease":
            passed = current_outflow < previous_outflow - epsilon
        elif expected == "maintain":
            passed = abs(current_outflow - previous_outflow) <= epsilon
        else:
            raise ValueError(f"未知 direction expected: {expected}")

        return {
            "pass": passed,
            "constraint_violations": 0 if passed else 1,
            "response_direction_correct": passed,
            "partial_credit": 1.0 if passed else 0.0,
            "detail": (
                f"direction: previous={previous_outflow:.1f}, actual={current_outflow:.1f}, "
                f"expected={expected}"
            ),
        }

    if condition_type == "best_effort":
        primary = _evaluate_pass_condition(
            condition["primary"],
            llm_outflow,
            state_before,
            state_after_sim,
        )
        safety = _evaluate_pass_condition(
            condition["safety_constraint"],
            llm_outflow,
            state_before,
            state_after_sim,
        )
        target = float(
            condition["primary"].get("max_flow", condition["primary"].get("target", llm_outflow))
        )
        tolerance_multiplier = float(condition.get("tolerance_multiplier", 2.0))
        worst_case = target * tolerance_multiplier
        partial_credit = _partial_credit(float(llm_outflow), target, worst_case)

        return {
            "pass": safety["pass"],
            "constraint_violations": (0 if safety["pass"] else 1) + (0 if primary["pass"] else 1),
            "response_direction_correct": primary["response_direction_correct"],
            "partial_credit": partial_credit,
            "detail": (
                f"best_effort: safety=({safety['detail']}), primary=({primary['detail']}), "
                f"partial_credit={partial_credit:.4f}"
            ),
        }

    raise ValueError(f"不支持的 pass_condition 类型: {condition_type}")


def evaluate_instruction_compliance(
    trigger: dict,
    llm_outflow: float,
    state_before: dict,
    state_after_sim: dict,
) -> dict:
    """
    评估 LLM 响应是否达到本次指令目标。

    Pass 条件完全由 trigger["pass_condition"] 驱动，无场景硬编码。
    """
    result = _evaluate_pass_condition(
        trigger["pass_condition"],
        llm_outflow,
        state_before,
        state_after_sim,
    )
    return {
        "pass": bool(result["pass"]),
        "constraint_violations": int(result["constraint_violations"]),
        "response_direction_correct": bool(result["response_direction_correct"]),
        "is_hard_task": bool(trigger.get("is_hard_task", False)),
        "partial_credit": round(float(result["partial_credit"]), 4),
        "detail": result["detail"],
    }


class ExperimentEvaluator:
    """
    对比人工调度与 MCP Agent 调度，使用 pyresops EvaluationService 计算评估指标。
    供实验评估辅助流程调用。
    """

    def compare(self, human_result: dict, mcp_result: dict, scenario: dict) -> dict:
        """
        计算单场景对比指标。

        Args:
            human_result: HumanBaselineScheduler.schedule() 的输出
            mcp_result:   运行时调度器 run_scenario() 的输出
            scenario:     场景参数字典

        Returns:
            对比评估字典
        """
        spec = _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))

        h_outflow = human_result.get("outflow", scenario["inflow"])
        m_outflow = mcp_result.get("outflow", scenario["inflow"])

        # 使用 pyresops 真实评估
        h_eval = _run_pyresops_eval(scenario, h_outflow, spec)
        m_eval = _run_pyresops_eval(scenario, m_outflow, spec)

        return {
            # 人工调度指标
            "human_overall": h_eval["overall_score"],
            "human_safety": h_eval["flood_control_score"],
            "human_benefit": h_eval["power_generation_score"],
            "human_eco_score": h_eval["ecological_score"],
            "human_supply_score": h_eval["water_supply_score"],
            "human_violations": h_eval["constraint_violations"],
            "human_outflow": h_outflow,
            # MCP 调度指标
            "mcp_overall": m_eval["overall_score"],
            "mcp_safety": m_eval["flood_control_score"],
            "mcp_benefit": m_eval["power_generation_score"],
            "mcp_eco_score": m_eval["ecological_score"],
            "mcp_supply_score": m_eval["water_supply_score"],
            "mcp_violations": m_eval["constraint_violations"],
            "mcp_outflow": m_outflow,
            # 仿真详情（人工）
            "human_sim": {k: v for k, v in h_eval.items() if k.startswith("sim_")},
            # 仿真详情（MCP）
            "mcp_sim": {k: v for k, v in m_eval.items() if k.startswith("sim_")},
        }

    def summarize(self, results: list[dict]) -> dict:
        """
        汇总所有场景统计，输出论文表格所需格式。

        Args:
            results: 实验流程累积的 results 列表，
                     每项包含 {"scenario", "human", "mcp", "evaluation"}

        Returns:
            汇总统计字典
        """
        n = len(results)
        if n == 0:
            return {}

        def avg(lst):
            return round(sum(lst) / len(lst), 4) if lst else 0.0

        def pct_improve(base: float, new: float) -> float:
            if base == 0:
                return 0.0
            return round((new - base) / base * 100, 2)

        h_overall = [r["evaluation"]["human_overall"] for r in results]
        m_overall = [r["evaluation"]["mcp_overall"] for r in results]
        h_safety = [r["evaluation"]["human_safety"] for r in results]
        m_safety = [r["evaluation"]["mcp_safety"] for r in results]
        h_benefit = [r["evaluation"]["human_benefit"] for r in results]
        m_benefit = [r["evaluation"]["mcp_benefit"] for r in results]
        h_eco = [r["evaluation"].get("human_eco_score", 0) for r in results]
        m_eco = [r["evaluation"].get("mcp_eco_score", 0) for r in results]
        h_supply = [r["evaluation"].get("human_supply_score", 0) for r in results]
        m_supply = [r["evaluation"].get("mcp_supply_score", 0) for r in results]
        h_viol = [r["evaluation"].get("human_violations", 0) for r in results]
        m_viol = [r["evaluation"].get("mcp_violations", 0) for r in results]

        h_time = [r["human"].get("decision_time", 0) for r in results]
        m_time = [
            r["mcp"].get("decision_time", r["mcp"].get("total_time_seconds", 0)) for r in results
        ]
        m_calls = [r["mcp"].get("tool_call_count", r["mcp"].get("tool_calls", 0)) for r in results]

        return {
            "total_scenarios": n,
            # 人工调度平均
            "human_avg_overall": avg(h_overall),
            "human_avg_safety": avg(h_safety),
            "human_avg_benefit": avg(h_benefit),
            "human_avg_eco": avg(h_eco),
            "human_avg_supply": avg(h_supply),
            "human_avg_violations": avg(h_viol),
            "human_avg_time": avg(h_time),
            # MCP 调度平均
            "mcp_avg_overall": avg(m_overall),
            "mcp_avg_safety": avg(m_safety),
            "mcp_avg_benefit": avg(m_benefit),
            "mcp_avg_eco": avg(m_eco),
            "mcp_avg_supply": avg(m_supply),
            "mcp_avg_violations": avg(m_viol),
            "mcp_avg_time": avg(m_time),
            "mcp_avg_tool_calls": avg(m_calls),
            # 相对改进（正数=MCP更好）
            "overall_improvement": pct_improve(avg(h_overall), avg(m_overall)),
            "safety_improvement": pct_improve(avg(h_safety), avg(m_safety)),
            "benefit_improvement": pct_improve(avg(h_benefit), avg(m_benefit)),
            "eco_improvement": pct_improve(avg(h_eco), avg(m_eco)),
            "supply_improvement": pct_improve(avg(h_supply), avg(m_supply)),
            # 违反约束减少量（负数=MCP违反更少，是好事）
            "violations_delta": round(avg(m_viol) - avg(h_viol), 4),
        }


class DynamicAdjustmentEvaluator:
    """评估 LLM 动态调整能力的核心指标。

    用于动态场景（S01/S02/S03）：对比调整前后的关键决策变量变化量、
    约束达成率趋势，判断 LLM 是否有效响应了突发事件。
    """

    # 总约束数（死水位、正常蓄水位、生态流量）
    TOTAL_CONSTRAINTS = 3

    def compute_adjustment_delta(self, before: dict, after: dict) -> dict:
        """计算调整前后关键决策变量变化量。

        Args:
            before: 调整前评估结果字典（含 outflow 字段）
            after:  调整后评估结果字典（含 outflow 字段）

        Returns:
            包含 outflow_change（绝对变化量）和 outflow_change_pct（百分比）的字典
        """
        before_outflow = before.get("outflow", 0.0)
        after_outflow = after.get("outflow", 0.0)
        outflow_change = round(after_outflow - before_outflow, 1)
        outflow_change_pct = (
            round(outflow_change / before_outflow * 100, 2) if before_outflow != 0 else 0.0
        )
        return {
            "outflow_change": outflow_change,
            "outflow_change_pct": outflow_change_pct,
        }

    def compute_constraint_achievement_rate(self, eval_result: dict) -> float:
        """计算约束达成率（无违反约束数 / 总约束数）。

        Args:
            eval_result: _run_pyresops_eval() 或 EvaluationService 返回的字典，
                         需包含 constraint_violations 字段

        Returns:
            0.0 ~ 1.0 之间的浮点数，1.0 表示全部约束达成
        """
        violations = eval_result.get("constraint_violations", 0)
        achieved = max(0, self.TOTAL_CONSTRAINTS - violations)
        return round(achieved / self.TOTAL_CONSTRAINTS, 4)

    def assess_adjustment_effectiveness(self, before_rate: float, after_rate: float) -> str:
        """判断调整有效性。

        Args:
            before_rate: 调整前约束达成率（0~1）
            after_rate:  调整后约束达成率（0~1）

        Returns:
            'improved'   — 调整后约束达成率显著提升（>0.01）
            'maintained' — 约束达成率基本持平（±0.01 以内）
            'degraded'   — 调整后约束达成率下降（<-0.01）
        """
        diff = after_rate - before_rate
        if diff > 0.01:
            return "improved"
        elif diff < -0.01:
            return "degraded"
        else:
            return "maintained"

    def compare_dynamic_scenario(self, before_result: dict, after_result: dict) -> dict:
        """生成动态场景完整对比报告。

        Args:
            before_result: 调整前的完整结果字典（含 outflow、constraint_violations、scores）
            after_result:  调整后的完整结果字典（同上）

        Returns:
            包含 adjustment_delta、constraint_achievement_rate、adjustment_effective 的字典
        """
        before_eval = {
            "outflow": before_result.get("outflow", 0.0),
            "constraint_violations": before_result.get("constraint_violations", 0),
        }
        after_eval = {
            "outflow": after_result.get("outflow", 0.0),
            "constraint_violations": after_result.get("constraint_violations", 0),
        }

        delta = self.compute_adjustment_delta(before_eval, after_eval)
        before_rate = self.compute_constraint_achievement_rate(before_eval)
        after_rate = self.compute_constraint_achievement_rate(after_eval)
        trend = self.assess_adjustment_effectiveness(before_rate, after_rate)

        return {
            "adjustment_delta": delta,
            "constraint_achievement_rate": {
                "before": before_rate,
                "after": after_rate,
                "trend": trend,
            },
            "adjustment_effective": after_rate >= before_rate,
            "score_change": round(
                after_result.get("scores", {}).get("overall", 0.0)
                - before_result.get("scores", {}).get("overall", 0.0),
                4,
            ),
        }
