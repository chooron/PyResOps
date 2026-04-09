"""
论文实验运行器（agno 框架 + pyresops 真实库版本）

核心思路：
  - agno @tool 包装 pyresops 真实服务（SimulationEngine、EvaluationService 等）
  - 五个调度场景均基于滩坑水电站真实参数（《2025年度水库控制运用计划》）
  - Agent 通过工具调用完成完整的调度分析流程
"""

from __future__ import annotations

import os
import sys
import json
import time
from datetime import datetime, timedelta

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# 滩坑水电站规格（复用自 scenarios/verify_*.py）
# ============================================================


def _build_tankan_spec(flood_limit_level: float = 156.5):
    """
    构建滩坑水电站规格。
    flood_limit_level: 台汛期 156.5m，梅汛期 160.0m
    """
    from pyresops.domain.reservoir import (
        DischargeCapacity,
        LevelStorageCurve,
        ReservoirSpec,
    )

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


# ============================================================
# 五个实验场景定义（与论文对应）
# ============================================================

SCENARIOS = [
    {
        "id": "S01",
        "name": "Typhoon Season Pre-release Dispatch",
        "description": "During typhoon season, reservoir level exceeds flood limit (156.5m); pre-release is required to create flood-control storage.",
        "flood_limit_level": 156.5,
        "current_level": 157.5,
        "initial_storage": 33.10,
        "initial_inflow": 300.0,
        "season": "typhoon",
        "flood_risk": "medium",
        "inflow": 300.0,
        "target_level": 156.5,
        "duration_hours": 48,
        "time_step_hours": 3,
    },
    {
        "id": "S02",
        "name": "Plum Flood Season Peak-shaving Dispatch",
        "description": "Perform peak-shaving in plum flood season and control Hecheng station flow at <= 14000 m3/s.",
        "flood_limit_level": 160.0,
        "current_level": 159.8,
        "initial_storage": 35.09,
        "initial_inflow": 1200.0,
        "season": "plum_flood",
        "flood_risk": "high",
        "inflow": 3380.0,  # 洪峰入库
        "target_level": 160.0,
        "duration_hours": 48,
        "time_step_hours": 3,
    },
    {
        "id": "S03",
        "name": "Extreme Flood Emergency Dispatch",
        "description": "Handle beyond-design flood conditions when water level exceeds design flood level (165.87m).",
        "flood_limit_level": 160.0,
        "current_level": 163.0,
        "initial_storage": 39.37,
        "initial_inflow": 5000.0,
        "season": "plum_flood",
        "flood_risk": "extreme",
        "inflow": 8000.0,
        "target_level": 165.87,
        "duration_hours": 72,
        "time_step_hours": 3,
    },
    {
        "id": "S04",
        "name": "Dry Season Power Generation Optimization",
        "description": "Maximize power generation in dry season while satisfying minimum ecological release.",
        "flood_limit_level": 156.5,
        "current_level": 150.0,
        "initial_storage": 28.72,
        "initial_inflow": 80.0,
        "season": "dry",
        "flood_risk": "none",
        "inflow": 70.0,
        "target_level": 145.0,
        "duration_hours": 24 * 30,  # 30天
        "time_step_hours": 24,
    },
    {
        "id": "S05",
        "name": "Plum-to-Typhoon Transition Drawdown",
        "description": "During transition from plum flood to typhoon season, reduce level from 160.0m to 156.5m.",
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


# ============================================================
# agno @tool 包装（调用 pyresops 真实服务）
# ============================================================


def _make_tools(spec):
    """
    构建绑定了特定 ReservoirSpec 的 agno 工具列表。
    延迟导入 agno，避免未安装时模块加载失败。
    """
    from agno.tools import tool as agno_tool

    @agno_tool
    def get_reservoir_status(scenario_id: str) -> str:
        """
        获取水库当前状态快照。
        返回：水位、库容、入库流量、汛限水位、死水位、正常蓄水位等信息。
        """
        sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if sc is None:
            return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)
        return json.dumps(
            {
                "scenario_id": scenario_id,
                "current_level_m": sc["current_level"],
                "initial_storage_billion_m3": sc["initial_storage"],
                "current_inflow_m3s": sc["inflow"],
                "dead_level_m": spec.dead_level,
                "normal_level_m": spec.normal_level,
                "flood_limit_level_m": sc["flood_limit_level"],
                "design_flood_level_m": spec.design_flood_level,
                "total_capacity_billion_m3": spec.total_capacity,
                "flood_capacity_billion_m3": spec.flood_capacity,
                "season": sc["season"],
                "flood_risk": sc["flood_risk"],
            },
            ensure_ascii=False,
            indent=2,
        )

    @agno_tool
    def simulate_dispatch_program(
        scenario_id: str,
        target_outflow: float,
        module_type: str = "constant_release",
    ) -> str:
        """
        使用 pyresops SimulationEngine 执行水量平衡仿真。

        Args:
            scenario_id: 场景ID（S01~S05）
            target_outflow: 目标出库流量（m³/s）
            module_type: 调度模块类型，可选 constant_release / flexible_release

        Returns:
            仿真结果JSON，包含最高水位、最低水位、平均出流、末水位等
        """
        from pyresops.core import SimulationEngine
        from pyresops.domain.forecast import ForecastBundle, ForecastSeries
        from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
        from pyresops.domain.reservoir import ReservoirState
        from pyresops.modules import ConstantReleaseModule, FlexibleReleaseModule

        sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if sc is None:
            return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

        start = datetime(2025, 6, 1, 0, 0, 0)
        step_seconds = sc["time_step_hours"] * 3600
        n_steps = sc["duration_hours"] // sc["time_step_hours"]
        end = start + timedelta(hours=sc["duration_hours"])

        state = ReservoirState(
            timestamp=start,
            level=sc["current_level"],
            storage=sc["initial_storage"],
            inflow=sc["initial_inflow"],
            outflow=sc["initial_inflow"],
        )

        # 构造入流预报（简化：线性插值）
        inflow_base = sc["inflow"]
        timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
        values = [float(inflow_base)] * n_steps
        forecast = ForecastBundle(
            forecast_time=start,
            series=[
                ForecastSeries(
                    variable="inflow",
                    timestamps=timestamps,
                    values=values,
                    unit="m³/s",
                )
            ],
        )

        horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)
        program = DispatchProgram(
            id=f"{scenario_id}_sim",
            name=f"{sc['name']} 仿真",
            time_horizon=horizon,
            module_sequence=[
                ModuleInstance(
                    id="m01",
                    module_type=module_type,
                    parameters={
                        "target_flow": target_outflow,
                        "target_outflow": target_outflow,
                        "min_flow": 50.0,
                        "max_flow": spec.discharge_capacity.get_max_discharge(sc["current_level"]),
                    },
                )
            ],
        )

        if module_type == "flexible_release":
            release_vals = [float(target_outflow)] * n_steps
            modules_map = {
                "flexible_release": FlexibleReleaseModule(
                    {
                        "control_interval_seconds": step_seconds,
                        "release_values": release_vals,
                    }
                )
            }
        else:
            modules_map = {
                "constant_release": ConstantReleaseModule({"target_flow": target_outflow})
            }

        engine = SimulationEngine(spec)
        result = engine.simulate(program, state, forecast, modules_map)

        snapshots_summary = [
            {
                "step": i,
                "timestamp": snap.timestamp.isoformat(),
                "level_m": round(snap.level, 3),
                "inflow_m3s": round(snap.inflow, 1),
                "outflow_m3s": round(snap.outflow, 1),
            }
            for i, snap in enumerate(result.snapshots[:: max(1, len(result.snapshots) // 10)])
        ]

        return json.dumps(
            {
                "scenario_id": scenario_id,
                "target_outflow": target_outflow,
                "max_level_m": round(result.max_level, 3),
                "min_level_m": round(result.min_level, 3),
                "final_level_m": round(result.snapshots[-1].level, 3),
                "avg_outflow_m3s": round(result.avg_outflow, 1),
                "total_steps": len(result.snapshots),
                "snapshots_sample": snapshots_summary,
            },
            ensure_ascii=False,
            indent=2,
        )

    @agno_tool
    def evaluate_dispatch_result(
        scenario_id: str,
        target_outflow: float,
        eco_min_flow: float = 50.0,
    ) -> str:
        """
        使用 pyresops EvaluationService 评估调度方案效果。

        Args:
            scenario_id: 场景ID
            target_outflow: 目标出库流量（m³/s）
            eco_min_flow: 生态最小流量要求（m³/s），默认50

        Returns:
            评估结果JSON，包含综合评分、防洪评分、供水评分、发电评分、生态评分
        """
        from pyresops.core import SimulationEngine
        from pyresops.domain.constraint import Constraint, ConstraintSet
        from pyresops.domain.forecast import ForecastBundle, ForecastSeries
        from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
        from pyresops.domain.reservoir import ReservoirState
        from pyresops.modules import ConstantReleaseModule
        from pyresops.services import EvaluationService

        sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if sc is None:
            return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

        start = datetime(2025, 6, 1, 0, 0, 0)
        step_seconds = sc["time_step_hours"] * 3600
        n_steps = sc["duration_hours"] // sc["time_step_hours"]
        end = start + timedelta(hours=sc["duration_hours"])

        state = ReservoirState(
            timestamp=start,
            level=sc["current_level"],
            storage=sc["initial_storage"],
            inflow=sc["initial_inflow"],
            outflow=sc["initial_inflow"],
        )

        timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
        forecast = ForecastBundle(
            forecast_time=start,
            series=[
                ForecastSeries(
                    variable="inflow",
                    timestamps=timestamps,
                    values=[float(sc["inflow"])] * n_steps,
                    unit="m³/s",
                )
            ],
        )

        horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)
        program = DispatchProgram(
            id=f"{scenario_id}_eval",
            name=f"{sc['name']} 评估",
            time_horizon=horizon,
            module_sequence=[
                ModuleInstance(
                    id="m01",
                    module_type="constant_release",
                    parameters={"target_flow": target_outflow},
                )
            ],
        )

        modules_map = {"constant_release": ConstantReleaseModule({"target_flow": target_outflow})}
        engine = SimulationEngine(spec)
        sim_result = engine.simulate(program, state, forecast, modules_map)

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
                    constraint_type="ecological_min_flow",
                    parameters={"min_flow": eco_min_flow},
                    priority=9,
                ),
            ]
        )

        ev = EvaluationService(spec)
        eval_result = ev.evaluate(sim_result, constraint_set=constraint_set)

        return json.dumps(
            {
                "scenario_id": scenario_id,
                "target_outflow": target_outflow,
                "overall_score": round(eval_result.overall_score, 4),
                "flood_control_score": round(eval_result.flood_control_score, 4),
                "water_supply_score": round(eval_result.water_supply_score, 4),
                "power_generation_score": round(eval_result.power_generation_score, 4),
                "ecological_score": round(eval_result.ecological_score, 4),
                "constraint_violations_count": len(eval_result.constraint_violations),
                "constraint_violations": eval_result.constraint_violations[:5],
            },
            ensure_ascii=False,
            indent=2,
        )

    @agno_tool
    def check_safety_constraints(
        scenario_id: str,
        proposed_outflow: float,
    ) -> str:
        """
        检查约束合规性：验证出库流量是否满足安全约束。

        Args:
            scenario_id: 场景ID
            proposed_outflow: 拟议出库流量（m³/s）

        Returns:
            约束检查结果JSON，包含各项约束是否满足及违反详情
        """
        sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if sc is None:
            return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

        violations = []
        checks = {}

        # 1. 泄流能力检查
        max_discharge = spec.discharge_capacity.get_max_discharge(sc["current_level"])
        if proposed_outflow > max_discharge:
            violations.append(
                f"出库 {proposed_outflow} m³/s 超过当前水位泄流能力 {max_discharge:.1f} m³/s"
            )
        checks["discharge_capacity"] = {
            "ok": proposed_outflow <= max_discharge,
            "proposed": proposed_outflow,
            "max_allowed": round(max_discharge, 1),
        }

        # 2. 生态流量检查
        eco_min = 50.0
        checks["ecological_flow"] = {
            "ok": proposed_outflow >= eco_min,
            "proposed": proposed_outflow,
            "min_required": eco_min,
        }
        if proposed_outflow < eco_min:
            violations.append(f"出库 {proposed_outflow} m³/s 低于生态最小流量 {eco_min} m³/s")

        # 3. 汛限水位检查
        if (
            sc["flood_risk"] in ("high", "extreme")
            and sc["current_level"] > sc["flood_limit_level"]
        ):
            recommended_min_outflow = sc["inflow"] * 0.8
            if proposed_outflow < recommended_min_outflow:
                violations.append(
                    f"防洪高风险时出库 {proposed_outflow} m³/s 偏小，"
                    f"建议 ≥ {recommended_min_outflow:.0f} m³/s"
                )
        checks["flood_risk_compliance"] = {
            "flood_risk": sc["flood_risk"],
            "current_level_m": sc["current_level"],
            "flood_limit_level_m": sc["flood_limit_level"],
            "level_above_limit": round(sc["current_level"] - sc["flood_limit_level"], 2),
        }

        return json.dumps(
            {
                "scenario_id": scenario_id,
                "proposed_outflow": proposed_outflow,
                "safe": len(violations) == 0,
                "violations": violations,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        )

    @agno_tool
    def optimize_release_plan(
        scenario_id: str,
        horizon_hours: int = 24,
        min_flow: float = 50.0,
        max_flow: float = 5000.0,
    ) -> str:
        """
        使用 pyresops OptimizationService 优化下泄计划。

        Args:
            scenario_id: 场景ID
            horizon_hours: 优化时段（小时），默认24小时
            min_flow: 最小下泄流量约束（m³/s）
            max_flow: 最大下泄流量约束（m³/s）

        Returns:
            优化后的分段下泄计划JSON
        """
        from pyresops.domain.forecast import ForecastBundle, ForecastSeries
        from pyresops.domain.reservoir import ReservoirState
        from pyresops.services import OptimizationService, ProgramService

        sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if sc is None:
            return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

        start = datetime(2025, 6, 1, 0, 0, 0)
        step_seconds = sc["time_step_hours"] * 3600
        n_steps = horizon_hours // sc["time_step_hours"]

        state = ReservoirState(
            timestamp=start,
            level=sc["current_level"],
            storage=sc["initial_storage"],
            inflow=sc["initial_inflow"],
            outflow=sc["initial_inflow"],
        )

        timestamps = [start + timedelta(seconds=i * step_seconds) for i in range(n_steps)]
        forecast = ForecastBundle(
            forecast_time=start,
            series=[
                ForecastSeries(
                    variable="inflow",
                    timestamps=timestamps,
                    values=[float(sc["inflow"])] * n_steps,
                    unit="m³/s",
                )
            ],
        )

        program_svc = ProgramService()
        opt_svc = OptimizationService(spec, program_svc)

        constraints = {
            "min_environmental_flow": min_flow,
            "max_outflow": max_flow,
            "min_release": min_flow,
        }
        objectives = {
            "power_priority": sc["flood_risk"] == "none",
            "flood_control": sc["flood_risk"] in ("high", "extreme"),
        }
        directives = {
            "safety_factor": 0.9 if sc["flood_risk"] in ("high", "extreme") else 0.85,
            "season": sc["season"],
        }

        program, schedule = opt_svc.optimize_flexible_release_plan(
            initial_state=state,
            forecast=forecast,
            horizon_hours=horizon_hours,
            control_interval_seconds=step_seconds,
            constraints=constraints,
            objectives=objectives,
            directives=directives,
            name=f"{sc['id']}_optimized",
        )

        return json.dumps(
            {
                "scenario_id": scenario_id,
                "program_id": program.id,
                "horizon_hours": horizon_hours,
                "n_segments": len(schedule.release_values),
                "release_values_m3s": [round(v, 1) for v in schedule.release_values],
                "avg_release_m3s": round(
                    sum(schedule.release_values) / len(schedule.release_values)
                    if schedule.release_values
                    else 0,
                    1,
                ),
                "min_release_m3s": round(
                    min(schedule.release_values) if schedule.release_values else 0, 1
                ),
                "max_release_m3s": round(
                    max(schedule.release_values) if schedule.release_values else 0, 1
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    @agno_tool
    def query_dispatch_rules(scenario_id: str) -> str:
        """
        查询适用于该场景的调度规程要求（来自《水库控制运用计划》）。

        Args:
            scenario_id: 场景ID

        Returns:
            适用规程条款和关键约束参数JSON
        """
        sc = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
        if sc is None:
            return json.dumps({"error": f"场景 {scenario_id} 不存在"}, ensure_ascii=False)

        rules_db = {
            "S01": {
                "场景": "台汛期预泄调度",
                "适用规程": "《2025年度水库控制运用计划》第3.1节 台汛期调度规则",
                "核心要求": [
                    "汛期限制水位 156.5m（7月1日至9月30日台汛期）",
                    "水位超过156.5m时须主动预泄至156.5m",
                    "预泄期间出库不超过下游安全泄量",
                    "台风预报48小时内须完成预泄",
                ],
                "关键参数": {
                    "flood_limit_level_m": 156.5,
                    "downstream_safe_flow_m3s": 14000,
                    "eco_min_flow_m3s": 50,
                    "max_discharge_at_160m_m3s": 5861,
                },
            },
            "S02": {
                "场景": "梅汛期错峰调度",
                "适用规程": "《2025年度水库控制运用计划》第3.2节 梅汛期调度规则",
                "核心要求": [
                    "梅汛期限制水位 160.0m（4月1日至6月30日）",
                    "水位在160~161.5m时执行补偿凑泄，控鹤城站≤14000 m³/s",
                    "马斯京根算法演算传播时间约5小时",
                    "错峰调度须提前5小时预报区间流量",
                ],
                "关键参数": {
                    "flood_limit_level_m": 160.0,
                    "hecheng_safe_flow_m3s": 14000,
                    "muskingum_propagation_hours": 5,
                    "max_level_for_spill_m": 161.5,
                    "eco_min_flow_m3s": 50,
                },
            },
            "S03": {
                "场景": "极端洪水应急调度",
                "适用规程": "《2025年度水库控制运用计划》第4节 超标准洪水应急预案",
                "核心要求": [
                    "水位超设计洪水位(165.87m)时启动应急预案",
                    "全力开启溢洪道，最大泄洪能力11085 m³/s",
                    "向下游发布预警，疏散安全区群众",
                    "水库大坝安全优先，允许下游超安全流量",
                ],
                "关键参数": {
                    "design_flood_level_m": 165.87,
                    "check_flood_level_m": 169.15,
                    "max_discharge_at_165m_m3s": 11085,
                    "emergency_trigger_level_m": 165.87,
                },
            },
            "S04": {
                "场景": "枯水期发电优化",
                "适用规程": "《2025年度水库控制运用计划》第5节 枯水期发电调度",
                "核心要求": [
                    "死水位以上（120m）最大化发电量",
                    "最小下泄流量不低于50 m³/s（生态基流）",
                    "水位低于135m时降低出力，保护水位",
                    "额定发电流量约400 m³/s（机组满发）",
                ],
                "关键参数": {
                    "dead_level_m": 120.0,
                    "eco_min_flow_m3s": 50,
                    "rated_power_flow_m3s": 400,
                    "low_level_threshold_m": 135.0,
                    "low_level_power_flow_m3s": 80,
                },
            },
            "S05": {
                "场景": "梅台过渡期降水位",
                "适用规程": "《2025年度水库控制运用计划》第3.3节 汛期过渡规则",
                "核心要求": [
                    "6月30日～7月1日梅汛期转台汛期",
                    "水位须从160m降至156.5m，预留防洪库容",
                    "3天内完成降水位操作",
                    "降水位期间加大出库，同时监测下游",
                ],
                "关键参数": {
                    "start_level_m": 160.0,
                    "target_level_m": 156.5,
                    "level_drop_m": 3.5,
                    "transition_days": 3,
                    "eco_min_flow_m3s": 50,
                },
            },
        }

        rule_info = rules_db.get(scenario_id, {"error": f"未找到场景 {scenario_id} 的规程信息"})
        return json.dumps(rule_info, ensure_ascii=False, indent=2)

    return [
        get_reservoir_status,
        simulate_dispatch_program,
        evaluate_dispatch_result,
        check_safety_constraints,
        optimize_release_plan,
        query_dispatch_rules,
    ]


# ============================================================
# AgnoMCPExperiment — 供 run_experiments.py 调用
# ============================================================

SYSTEM_PROMPT = """You are a professional reservoir dispatch assistant for Tankan Hydropower Station.
You have a complete toolset for reservoir operations: querying current status, running water-balance simulation,
evaluating dispatch performance, checking safety constraints, optimizing release plans, and reading operation rules.

Follow this workflow:
1. Query current reservoir status (get_reservoir_status)
2. Query applicable operation rules (query_dispatch_rules)
3. Check safety constraints for proposed release (check_safety_constraints)
4. Run dispatch simulation (simulate_dispatch_program)
5. Evaluate dispatch performance (evaluate_dispatch_result)
6. Optimize release plan if needed (optimize_release_plan)
7. Provide final dispatch decision including release recommendation, safety assessment, and benefit analysis

Please provide responses in English and keep recommendations rule-compliant and safety-first."""


def _load_model_config(profile: str | None = None, config_path: str | None = None):
    """
    从 config.yml 加载模型配置。

    Args:
        profile: 模型配置名称（如 "deepseek", "qwen", "minimax", "openai", "claude"）
                 若为 None，则使用 config.yml 中的 default_profile
        config_path: config.yml 路径，默认为 experiments/config.yml

    Returns:
        dict: 模型配置字典，包含 provider, model_id, api_key, base_url 等字段
    """
    import os
    import pathlib

    try:
        import yaml
    except ImportError:
        raise ImportError("请安装 PyYAML：pip install pyyaml")

    if config_path is None:
        # 默认路径：当前文件同目录下的 config.yml
        config_path = pathlib.Path(__file__).parent / "config.yml"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 确定使用哪个 profile
    if profile is None:
        profile = cfg.get("default_profile", "claude")

    models_cfg = cfg.get("models", {})
    if profile not in models_cfg:
        available = list(models_cfg.keys())
        raise ValueError(f"模型配置 '{profile}' 不存在，可用配置：{available}")

    model_cfg = models_cfg[profile].copy()

    # 从环境变量读取 API Key
    api_key_env = model_cfg.pop("api_key_env", None)
    if "api_key" not in model_cfg and api_key_env:
        api_key = os.getenv(api_key_env)
        if api_key:
            model_cfg["api_key"] = api_key

    return model_cfg


def _build_agno_model(model_cfg: dict):
    """
    根据模型配置字典构建 agno 模型实例。

    支持的 provider：
        - anthropic   → agno.models.anthropic.Claude
        - deepseek    → agno.models.deepseek.DeepSeek
        - dashscope   → agno.models.dashscope.DashScope（通义千问）
        - openai_like → agno.models.openai.OpenAILike（MiniMax、OpenAI 自定义地址等）
    """
    provider = model_cfg.get("provider", "anthropic")
    model_id = model_cfg.get("model_id", "")
    api_key = model_cfg.get("api_key")
    base_url = model_cfg.get("base_url")

    if provider == "anthropic":
        from agno.models.anthropic import Claude

        kwargs = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        return Claude(**kwargs)

    elif provider == "deepseek":
        from agno.models.deepseek import DeepSeek

        kwargs = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return DeepSeek(**kwargs)

    elif provider == "dashscope":
        from agno.models.dashscope import DashScope

        kwargs = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return DashScope(**kwargs)

    elif provider == "openai_like":
        from agno.models.openai.like import OpenAILike

        kwargs = {"id": model_id}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAILike(**kwargs)

    else:
        raise ValueError(
            f"不支持的 provider: '{provider}'，可选：anthropic, deepseek, dashscope, openai_like"
        )


class AgnoMCPExperiment:
    """
    agno 框架封装的 MCP Agent 实验类（使用 pyresops 真实库）。
    供 run_experiments.py 调用。

    模型通过 config.yml 配置文件加载，支持：
        - anthropic  (Claude)
        - deepseek   (DeepSeek / DeepSeek-R1)
        - dashscope  (通义千问 Qwen)
        - openai_like (MiniMax、OpenAI 自定义代理等)

    示例：
        # 使用 config.yml 中 default_profile 指定的模型
        exp = AgnoMCPExperiment()

        # 使用 deepseek profile
        exp = AgnoMCPExperiment(model_profile="deepseek")

        # 使用 minimax profile
        exp = AgnoMCPExperiment(model_profile="minimax")
    """

    def __init__(
        self,
        model_profile: str | None = None,
        config_path: str | None = None,
    ):
        """
        Args:
            model_profile: config.yml 中的模型配置名称，None 则使用 default_profile
            config_path: config.yml 路径，None 则使用 experiments/config.yml
        """
        self._model_cfg = _load_model_config(profile=model_profile, config_path=config_path)
        self.model_id = self._model_cfg.get("model_id", "unknown")
        self.model_profile = model_profile

    def _get_spec(self, scenario: dict):
        """获取对应场景的 ReservoirSpec（延迟构建）."""
        return _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))

    def _build_agent(self, spec):
        """构建 agno Agent（延迟导入）."""
        from agno.agent import Agent

        model = _build_agno_model(self._model_cfg)
        tools = _make_tools(spec)
        return Agent(
            model=model,
            tools=tools,
            description=SYSTEM_PROMPT,
            markdown=False,
        )

    def run_scenario(self, scenario: dict) -> dict:
        """
        运行单个场景，返回与 run_experiments.py 兼容的结果字典。
        """
        import re

        start_time = time.time()

        spec = self._get_spec(scenario)

        user_message = (
            f"Please perform a complete analysis for the following reservoir dispatch scenario and provide a final decision:\n\n"
            f"Scenario ID: {scenario['id']}\n"
            f"Scenario Name: {scenario['name']}\n"
            f"Scenario Description: {scenario['description']}\n\n"
            f"Current State:\n"
            f"- Inflow: {scenario['inflow']} m3/s\n"
            f"- Current Water Level: {scenario['current_level']} m\n"
            f"- Target Water Level: {scenario['target_level']} m\n"
            f"- Season: {scenario['season']}\n"
            f"- Flood Risk: {scenario['flood_risk']}\n\n"
            f"Use available tools for end-to-end analysis (status -> rules -> simulation -> evaluation), then provide the final dispatch plan in English."
        )

        agent = self._build_agent(spec)
        run_response = agent.run(user_message)
        total_time = time.time() - start_time

        final_text = (
            str(run_response.content)
            if hasattr(run_response, "content") and run_response.content
            else ""
        )

        # 提取工具调用信息
        tool_calls_detail = []
        tool_call_count = 0
        if hasattr(run_response, "tools") and run_response.tools:
            for i, tc in enumerate(run_response.tools, 1):
                if isinstance(tc, dict):
                    tool_name = tc.get("tool_name") or tc.get("name", "unknown")
                else:
                    tool_name = getattr(tc, "tool_name", None) or getattr(tc, "name", "unknown")
                tool_calls_detail.append({"call_order": i, "tool_name": tool_name})
            tool_call_count = len(tool_calls_detail)

        # 提取出库流量（从 Agent 回复文本中解析）
        outflow = scenario["inflow"]
        for pattern in [
            r"出库流量[：:]\s*(\d+\.?\d*)\s*m³/s",
            r"建议.*?(\d+\.?\d*)\s*m³/s",
            r"泄放\s*(\d+\.?\d*)\s*m³/s",
            r"目标出库.*?(\d+\.?\d*)",
            r"(?:release|outflow).*?(\d+\.?\d*)\s*m3/s",
            r"(?:recommended|recommend).*?(\d+\.?\d*)\s*m3/s",
            r"(?:target\s+)?outflow[\s:=]+(\d+\.?\d*)",
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
            "tool_call_count": tool_call_count,
            "tool_calls_detail": tool_calls_detail,
            "total_time_seconds": round(total_time, 3),
            "success": True,
        }


# ============================================================
# 统一实验入口
# ============================================================


def run_all(model_profile: str | None = None) -> dict:
    """
    统一实验入口：依次运行静态场景（S04/S05）和动态场景（S01/S02/S03）。

    Args:
        model_profile: 模型配置名称（对应 config.yml 中的 profile）

    Returns:
        包含 static_results 和 dynamic_results 的汇总字典
    """
    from static_experiment import run_static_experiments
    from dynamic_experiment import run_dynamic_experiments

    print("=" * 60)
    print("PyResOps 论文实验 — 统一入口")
    print("=" * 60)

    print("\n[1/2] 运行静态场景实验（S04、S05）...")
    static_results = run_static_experiments(model_profile=model_profile)

    print("\n[2/2] 运行动态场景实验（S01、S02、S03）...")
    dynamic_results = run_dynamic_experiments(model_profile=model_profile)

    report = summarize_all_results(static_results, dynamic_results)
    _save_report(report)
    return report


def summarize_all_results(
    static_results: list[dict],
    dynamic_results: list[dict],
) -> dict:
    """
    汇总静态和动态实验结果，生成论文所需的综合报告。

    Args:
        static_results:  run_static_experiments() 返回的结果列表
        dynamic_results: run_dynamic_experiments() 返回的结果列表

    Returns:
        综合报告字典
    """

    def avg(lst):
        return round(sum(lst) / len(lst), 4) if lst else 0.0

    # 静态场景汇总
    valid_static = [r for r in static_results if "error" not in r]
    static_summary = {
        "total": len(valid_static),
        "llm_avg_overall": avg([r["llm_scores"]["overall"] for r in valid_static]),
        "human_avg_overall": avg([r["human_scores"]["overall"] for r in valid_static]),
        "total_llm_violations": sum(r["llm_constraint_violations"] for r in valid_static),
        "process_complete_rate": avg([1.0 if r["process_complete"] else 0.0 for r in valid_static]),
    }

    # 动态场景汇总
    valid_dynamic = [r for r in dynamic_results if "error" not in r]
    dynamic_summary = {
        "total": len(valid_dynamic),
        "adjustment_effective_rate": avg(
            [1.0 if r.get("adjustment_effective") else 0.0 for r in valid_dynamic]
        ),
        "avg_constraint_rate_before": avg(
            [r["constraint_achievement_rate"]["before"] for r in valid_dynamic]
        ),
        "avg_constraint_rate_after": avg(
            [r["constraint_achievement_rate"]["after"] for r in valid_dynamic]
        ),
        "trends": [r["constraint_achievement_rate"]["trend"] for r in valid_dynamic],
    }

    return {
        "experiment_time": __import__("datetime").datetime.now().isoformat(),
        "static_summary": static_summary,
        "dynamic_summary": dynamic_summary,
        "static_results": static_results,
        "dynamic_results": dynamic_results,
    }


def _save_report(report: dict) -> None:
    """将综合报告保存到 results/ 目录."""
    from pathlib import Path

    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"full_report_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        __import__("json").dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n综合报告已保存: {out_path}")


if __name__ == "__main__":
    run_all()
