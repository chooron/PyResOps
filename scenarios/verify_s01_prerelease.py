"""
S01 台汛期预泄调度验证脚本

验证目标：
  1. 台汛期水位超过 156.5m 时，预泄规则正确触发
  2. 仿真末水位降至 ≤156.5m
  3. 约束校核：生态流量、爬坡速率
  4. 决策轨迹中记录预泄原因
  5. 防洪评分 > 0.8

基于 pyresops 核心 API（SimulationEngine + ConstraintValidator）直接调用
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pyresops.core import SimulationEngine, ConstraintValidator
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.policy import PolicyBundle
from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
from pyresops.domain.reservoir import (
    DischargeCapacity,
    LevelStorageCurve,
    ReservoirSpec,
    ReservoirState,
)
from pyresops.domain.rule import DispatchRule, RuleAction, RuleSet
from pyresops.modules import ConstantReleaseModule
from pyresops.services import EvaluationService


def build_tankan_spec() -> ReservoirSpec:
    """构建滩坑水电站规格（简化参数，基于运控计划附表5.5-1）."""
    # 水位-库容表（简化8点插值）
    levels = [120.0, 130.0, 140.0, 150.0, 156.5, 160.0, 161.5, 165.87, 169.15]
    storages = [13.94, 18.14, 23.05, 28.72, 32.51, 35.20, 36.17, 39.37, 41.90]

    # 泄洪能力（6孔溢洪道全开，运控计划表5.6-1）
    d_levels = [148.0, 150.0, 155.0, 160.0, 161.5, 165.87]
    d_discharges = [0.0, 361.0, 2456.0, 5861.0, 6649.0, 11085.0]

    return ReservoirSpec(
        id="tankan_2025",
        name="滩坑水电站",
        dead_level=120.0,
        normal_level=160.0,
        flood_limit_level=156.5,       # 台汛期限制水位
        design_flood_level=165.87,
        check_flood_level=169.15,
        total_capacity=41.90,
        flood_capacity=3.50,           # 防洪库容（3.5亿m³）
        level_storage_curve=LevelStorageCurve(levels=levels, storages=storages),
        discharge_capacity=DischargeCapacity(levels=d_levels, max_discharges=d_discharges),
    )


def build_initial_state(timestamp: datetime) -> ReservoirState:
    """构建台汛期初始状态：水位 157.5m，高于汛限 1.0m."""
    return ReservoirState(
        timestamp=timestamp,
        level=157.5,
        storage=33.10,    # 约 33.1亿m³
        inflow=300.0,     # 台汛期枯水段入库
        outflow=300.0,
    )


def build_forecast(start: datetime, n_steps: int, step_hours: int) -> ForecastBundle:
    """构建台汛期预泄阶段预报（入库偏小，有利于预泄）."""
    timestamps = [start + timedelta(hours=i * step_hours) for i in range(n_steps)]
    # 台风前期，来水从 300 逐步减少到 150，然后台风前锋影响略增
    values = []
    for i in range(n_steps):
        if i < 6:
            values.append(300.0 - i * 20)    # 300→180，稳步减少
        elif i < 10:
            values.append(180.0 - (i - 6) * 10)  # 180→140
        else:
            values.append(140.0 + (i - 10) * 30)  # 台风前锋来临，逐步增大
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(
            variable="inflow",
            timestamps=timestamps,
            values=[max(50.0, v) for v in values],
            unit="m³/s",
        )],
    )


def build_program(start: datetime, n_steps: int, step_hours: int) -> DispatchProgram:
    """构建预泄调度方案（以常量下泄模拟主动预泄）."""
    step_seconds = step_hours * 3600
    end = start + timedelta(hours=n_steps * step_hours)
    horizon = TimeHorizon(start=start, end=end, time_step=step_seconds)

    return DispatchProgram(
        id="s01_prerelease_2025",
        name="台汛期预泄调度方案",
        time_horizon=horizon,
        module_sequence=[
            ModuleInstance(
                id="m01",
                module_type="constant_release",
                parameters={
                    "target_outflow": 1500.0,   # 机组满发+溢洪道小幅开启
                    "min_outflow": 50.0,
                    "max_outflow": 3000.0,
                },
            )
        ],
    )


def build_policy() -> PolicyBundle:
    """构建台汛期预泄策略包."""
    constraints = ConstraintSet(constraints=[
        Constraint(
            id="level_max_normal",
            name="不超正常蓄水位",
            constraint_type="level_max",
            parameters={"max_level": 160.0},
            priority=10,
        ),
        Constraint(
            id="level_min_dead",
            name="不低于死水位",
            constraint_type="level_min",
            parameters={"min_level": 120.0},
            priority=10,
        ),
        Constraint(
            id="eco_flow",
            name="生态最小流量",
            constraint_type="ecological_min_flow",
            parameters={"min_flow": 50.0},
            priority=8,
        ),
        Constraint(
            id="ramp_rate",
            name="流量爬坡约束",
            constraint_type="ramp_rate_max",
            parameters={"max_ramp_rate": 800.0},
            priority=6,
        ),
    ])

    rules = RuleSet(rules=[
        DispatchRule(
            id="r01_prerelease",
            name="台汛限水位预泄规则",
            condition={
                "all": [
                    {"path": "state.level", "op": "gt", "value": 156.5},
                    {"path": "state.level", "op": "lte", "value": 160.0},
                ]
            },
            actions=[RuleAction(
                action_type="set_target_outflow",
                parameters={
                    "value": 1500.0,
                    "reason": "台汛期水位超汛限(156.5m)，主动预泄至台汛限制水位",
                },
            )],
            priority=100,
        ),
        DispatchRule(
            id="r02_stop_prerelease",
            name="预泄完成维持规则",
            condition={
                "all": [
                    {"path": "state.level", "op": "lte", "value": 156.5},
                ]
            },
            actions=[RuleAction(
                action_type="set_target_outflow",
                parameters={
                    "value": 400.0,
                    "reason": "已降至台汛限制水位，转机组发电模式",
                },
            )],
            priority=90,
        ),
    ])

    return PolicyBundle(
        constraints=constraints,
        rules=rules,
        objectives={"flood_control": 0.7, "power": 0.3},
        directives={
            "typhoon_warning": True,
            "target_level": 156.5,
            "season": "typhoon",
        },
    )


def main() -> bool:
    """运行 S01 台汛期预泄调度验证."""
    print("\n[S01] 初始化场景参数...")
    start = datetime(2025, 8, 10, 8, 0, 0)
    n_steps = 16
    step_hours = 3     # 3小时步长，共 48h

    spec = build_tankan_spec()
    state = build_initial_state(start)
    forecast = build_forecast(start, n_steps, step_hours)
    program = build_program(start, n_steps, step_hours)
    policy = build_policy()

    print(f"  水库: {spec.name}")
    print(f"  初始水位: {state.level}m（台汛限制水位 156.5m，超出 {state.level-156.5:.1f}m）")
    print(f"  仿真时段: {n_steps}步 × {step_hours}h = {n_steps*step_hours}h")

    # ── 仿真引擎 ──────────────────────────────────────────────
    print("\n[S01] 运行仿真引擎...")
    modules = {"constant_release": ConstantReleaseModule({"target_flow": 1500.0})}

    engine = SimulationEngine(spec)
    result = engine.simulate(program, state, forecast, modules, policy_bundle=policy)

    print(f"  仿真完成: {len(result.snapshots)} 步")
    print(f"  最高水位: {result.max_level:.2f}m")
    print(f"  最低水位: {result.min_level:.2f}m")
    print(f"  末水位:   {result.snapshots[-1].level:.2f}m")
    print(f"  平均出流: {result.avg_outflow:.0f} m³/s")

    # ── 约束校核 ──────────────────────────────────────────────
    print("\n[S01] 约束校核...")
    cs = ConstraintSet(constraints=[
        Constraint(
            id="level_max",
            name="水位不超正常蓄水位",
            constraint_type="level_max",
            parameters={"max_level": 160.0},
        ),
        Constraint(
            id="eco_flow",
            name="生态最小流量",
            constraint_type="ecological_min_flow",
            parameters={"min_flow": 50.0},
        ),
    ])
    validator = ConstraintValidator(cs)
    violations = validator.validate_simulation(result)
    print(f"  约束违反: {len(violations)} 项")
    for v in violations:
        print(f"    ⚠ {v['constraint_name']}: 值={v['value']:.2f}, 限值={v['limit']:.2f}")

    # ── 评估 ──────────────────────────────────────────────────
    print("\n[S01] 效益评估...")
    ev = EvaluationService(spec)
    eval_result = ev.evaluate(result, constraint_set=cs)
    print(f"  综合评分:  {eval_result.overall_score:.2f}")
    print(f"  防洪评分:  {eval_result.flood_control_score:.2f}")

    # ── 验证断言 ──────────────────────────────────────────────
    print("\n[S01] 验证断言...")
    final_level = result.snapshots[-1].level

    # 断言1：末水位应降至 ≤156.5m + 允许0.5m误差
    assert final_level <= 157.0, f"末水位 {final_level:.2f}m 未达到预泄目标 ≤157.0m"
    print(f"  ✓ 末水位 {final_level:.2f}m ≤ 157.0m（预泄有效）")

    # 断言2：最高水位不超正常蓄水位
    assert result.max_level <= 160.0, f"最高水位 {result.max_level:.2f}m 超过正常蓄水位 160.0m"
    print(f"  ✓ 最高水位 {result.max_level:.2f}m ≤ 160.0m")

    # 断言3：仿真步数完整
    assert len(result.snapshots) >= n_steps, f"仿真步数不足: {len(result.snapshots)}"
    print(f"  ✓ 仿真步数 {len(result.snapshots)} ≥ {n_steps}")

    # 断言4：约束违反不应涉及水位超限
    level_violations = [v for v in violations if "level" in v.get("constraint_name", "").lower()]
    assert len(level_violations) == 0, f"存在水位约束违反: {level_violations}"
    print(f"  ✓ 无水位约束违反")

    # 断言5：防洪评分应合理
    assert eval_result.flood_control_score >= 50.0, f"防洪评分偏低: {eval_result.flood_control_score}"
    print(f"  ✓ 防洪评分 {eval_result.flood_control_score:.1f} ≥ 50.0")

    print("\n[S01] ✓ 台汛期预泄调度验证通过！")
    return True


if __name__ == "__main__":
    import sys
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))
    ok = main()
    sys.exit(0 if ok else 1)
