"""
使用案例 1: 洪水调度全流程

演示从创建水库到完成一次洪水调度仿真的完整流程:
1. 定义水库参数
2. 创建初始状态
3. 构建洪水预报
4. 创建调度方案 (含模块切换)
5. 运行仿真
6. 约束校核
7. 评估与解释
"""

from datetime import datetime, timedelta

from res_ops.domain.reservoir import (
    ReservoirSpec,
    ReservoirState,
    LevelStorageCurve,
    DischargeCapacity,
)
from res_ops.domain.program import DispatchProgram, TimeHorizon, ModuleInstance, SwitchCondition
from res_ops.domain.forecast import ForecastBundle, ForecastSeries
from res_ops.domain.constraint import Constraint, ConstraintSet
from res_ops.core import SimulationEngine, ConstraintValidator
from res_ops.modules import ConstantReleaseModule, StorageDrivenModule, LevelTrackingModule
from res_ops.services import EvaluationService, ExplanationService


def main():
    print("=" * 70)
    print("使用案例 1: 洪水调度全流程")
    print("=" * 70)

    # ── 1. 定义水库 ──────────────────────────────────────────────
    spec = ReservoirSpec(
        id="case1_res",
        name="案例水库",
        dead_level=150.0,
        normal_level=175.0,
        flood_limit_level=155.0,
        design_flood_level=178.0,
        check_flood_level=182.0,
        total_capacity=39.3,
        flood_capacity=22.15,
        level_storage_curve=LevelStorageCurve(
            levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
            storages=[0.0, 10.0, 20.0, 30.0, 39.3, 51.6],
        ),
        discharge_capacity=DischargeCapacity(
            levels=[135.0, 145.0, 155.0, 165.0, 175.0, 185.0],
            max_discharges=[0.0, 5000.0, 10000.0, 15000.0, 20000.0, 30000.0],
        ),
    )
    print(f"\n[1] 水库: {spec.name}")
    print(f"    汛限水位: {spec.flood_limit_level}m  正常蓄水位: {spec.normal_level}m")

    # ── 2. 初始状态 ──────────────────────────────────────────────
    state = ReservoirState(
        timestamp=datetime(2024, 7, 10, 8, 0, 0),
        level=158.0,
        storage=22.0,
        inflow=6000.0,
        outflow=6000.0,
    )
    print(f"\n[2] 初始状态: 水位={state.level}m  库容={state.storage}亿m³  入流={state.inflow}m³/s")

    # ── 3. 洪水预报 (48h, 先涨后退) ──────────────────────────────
    start = datetime(2024, 7, 10, 8, 0, 0)
    peak_hour = 20
    peak_flow = 25000.0
    values = []
    for h in range(48):
        if h <= peak_hour:
            v = 6000 + (peak_flow - 6000) * (h / peak_hour)
        else:
            v = peak_flow - (peak_flow - 6000) * ((h - peak_hour) / (48 - peak_hour))
        values.append(v)

    forecast = ForecastBundle(
        forecast_time=start,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[start + timedelta(hours=h) for h in range(48)],
                values=values,
            )
        ],
    )
    print(f"\n[3] 洪水预报: 48h  峰值={peak_flow:.0f}m³/s (第{peak_hour}h)")

    # ── 4. 调度方案 (三阶段) ─────────────────────────────────────
    program = DispatchProgram(
        id="case1_program",
        name="三阶段洪水调度",
        time_horizon=TimeHorizon(start=start, end=start + timedelta(hours=47), time_step=3600),
        module_sequence=[
            # 阶段1: 预泄腾库
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 8000.0}),
            # 阶段2: 拦洪削峰 (跟踪汛限水位)
            ModuleInstance(
                module_type="level_tracking",
                parameters={
                    "target_level": 155.0,
                    "kp": 1000.0,
                    "min_outflow": 3000.0,
                    "max_outflow": 18000.0,
                },
            ),
            # 阶段3: 逐步回蓄
            ModuleInstance(
                module_type="storage_driven",
                parameters={
                    "low_storage_threshold": 0.4,
                    "high_storage_threshold": 0.8,
                    "base_flow": 5000.0,
                    "extra_release_rate": 0.2,
                },
            ),
        ],
        switch_conditions=[
            # 入流超 15000 -> 切换到拦洪
            SwitchCondition(
                from_module="constant_release",
                to_module="level_tracking",
                condition_type="inflow_threshold",
                parameters={"threshold": 15000.0, "direction": "above"},
            ),
            # 入流回落到 10000 以下 -> 切换到回蓄
            SwitchCondition(
                from_module="level_tracking",
                to_module="storage_driven",
                condition_type="inflow_threshold",
                parameters={"threshold": 10000.0, "direction": "below"},
            ),
        ],
    )
    print(f"\n[4] 调度方案: {program.name}")
    print(f"    阶段1: 预泄 (恒定8000m³/s)")
    print(f"    阶段2: 拦洪 (跟踪汛限水位155m)")
    print(f"    阶段3: 回蓄 (蓄水量驱动)")

    # ── 5. 仿真 ─────────────────────────────────────────────────
    engine = SimulationEngine(spec)
    modules = {
        "constant_release": ConstantReleaseModule({"target_flow": 8000.0}),
        "level_tracking": LevelTrackingModule(
            {
                "target_level": 155.0,
                "kp": 1000.0,
                "min_outflow": 3000.0,
                "max_outflow": 18000.0,
            }
        ),
        "storage_driven": StorageDrivenModule(
            {
                "low_storage_threshold": 0.4,
                "high_storage_threshold": 0.8,
                "base_flow": 5000.0,
                "extra_release_rate": 0.2,
            }
        ),
    }
    result = engine.simulate(program, state, forecast, modules)
    print(f"\n[5] 仿真完成: {len(result.snapshots)}步")
    print(f"    最高水位: {result.max_level:.2f}m")
    print(f"    最低水位: {result.min_level:.2f}m")
    print(f"    平均出流: {result.avg_outflow:.0f}m³/s")

    # ── 6. 约束校核 ──────────────────────────────────────────────
    cs = ConstraintSet(
        constraints=[
            Constraint(
                id="lmax",
                name="最高水位不超过设计洪水位",
                constraint_type="level_max",
                parameters={"max_level": spec.design_flood_level},
            ),
            Constraint(
                id="fmax",
                name="最大流量不超过20000",
                constraint_type="flow_max",
                parameters={"max_flow": 20000.0},
            ),
            Constraint(
                id="ws",
                name="供水流量不低于5000",
                constraint_type="water_supply",
                parameters={"demand": 5000.0},
            ),
        ]
    )
    validator = ConstraintValidator(cs)
    violations = validator.validate_simulation(result)
    print(f"\n[6] 约束校核: {len(violations)}项违反")
    for v in violations:
        print(
            f"    - {v['constraint_name']}: {v['violation_type']} "
            f"(实际={v['value']:.2f}, 限值={v['limit']:.2f})"
        )

    # ── 7. 评估与解释 ────────────────────────────────────────────
    ev_service = EvaluationService(spec)
    eval_result = ev_service.evaluate(result, constraint_set=cs, include_step_scores=True)
    print(f"\n[7] 评估结果:")
    print(f"    综合评分: {eval_result.overall_score:.1f}")
    print(f"    防洪评分: {eval_result.flood_control_score:.1f}")
    print(f"    供水分: {eval_result.water_supply_score:.1f}")
    print(f"    逐步评分: {len(eval_result.step_scores)}步")

    ex_service = ExplanationService()
    explanation = ex_service.explain_program(program, result, eval_result)
    print(f"\n    方案摘要: {explanation['summary']}")

    # 关键时刻输出
    print(f"\n    关键时刻:")
    print(f"    {'时刻':<20} {'水位(m)':<10} {'入流':<10} {'出流':<10} {'模块':<20}")
    print(f"    {'-' * 70}")
    for snap in result.snapshots[::6]:  # 每6小时
        print(
            f"    {snap.timestamp.strftime('%m-%d %H:%M'):<20} "
            f"{snap.level:<10.2f} {snap.inflow:<10.0f} {snap.outflow:<10.0f} "
            f"{snap.active_module or 'N/A':<20}"
        )

    print("\n" + "=" * 70)
    print("案例 1 完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
