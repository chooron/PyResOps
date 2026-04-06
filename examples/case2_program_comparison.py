"""
使用案例 2: 多方案比选

演示创建多个调度方案, 逐一仿真和评估, 然后比较选出最优方案:
1. 创建3个候选方案
2. 对每个方案运行仿真
3. 约束校核 + 评估
4. 横向比较选出最优
"""

from datetime import datetime, timedelta

from res_ops.domain.reservoir import (
    ReservoirSpec,
    ReservoirState,
    LevelStorageCurve,
    DischargeCapacity,
)
from res_ops.domain.program import TimeHorizon
from res_ops.domain.forecast import ForecastBundle, ForecastSeries
from res_ops.domain.constraint import Constraint, ConstraintSet
from res_ops.services import (
    SnapshotService,
    ProgramService,
    SimulationService,
    EvaluationService,
)


def main():
    print("=" * 70)
    print("使用案例 2: 多方案比选")
    print("=" * 70)

    # ── 水库与初始状态 ───────────────────────────────────────────
    spec = ReservoirSpec(
        id="compare_res",
        name="比选水库",
        dead_level=150.0,
        normal_level=175.0,
        flood_limit_level=155.0,
        design_flood_level=178.0,
        check_flood_level=182.0,
        total_capacity=39.3,
        flood_capacity=22.15,
        level_storage_curve=LevelStorageCurve(
            levels=[135, 145, 155, 165, 175, 185],
            storages=[0, 10, 20, 30, 39.3, 51.6],
        ),
        discharge_capacity=DischargeCapacity(
            levels=[135, 145, 155, 165, 175, 185],
            max_discharges=[0, 5000, 10000, 15000, 20000, 30000],
        ),
    )

    ss = SnapshotService()
    ps = ProgramService()
    sim_s = SimulationService(spec, ps.get_module_registry())
    ev_s = EvaluationService(spec)

    state = ss.create_initial_snapshot("res", spec, 160.0, 7000.0)

    # 洪水预报
    start = datetime(2024, 7, 15, 0, 0, 0)
    flood_values = [7000 + 1000 * i if i < 20 else 27000 - 1000 * (i - 20) for i in range(40)]
    forecast = ForecastBundle(
        forecast_time=start,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[start + timedelta(hours=h) for h in range(40)],
                values=flood_values,
            )
        ],
    )

    constraints = ConstraintSet(
        constraints=[
            Constraint(
                id="lmax",
                name="",
                constraint_type="level_max",
                parameters={"max_level": spec.design_flood_level},
            ),
            Constraint(
                id="fmax", name="", constraint_type="flow_max", parameters={"max_flow": 20000.0}
            ),
        ]
    )

    # ── 候选方案 ─────────────────────────────────────────────────
    candidates = [
        {
            "name": "方案A: 恒定下泄8000",
            "modules": [{"module_type": "constant_release", "parameters": {"target_flow": 8000}}],
        },
        {
            "name": "方案B: 蓄水量驱动(保守)",
            "modules": [
                {
                    "module_type": "storage_driven",
                    "parameters": {
                        "low_storage_threshold": 0.3,
                        "high_storage_threshold": 0.7,
                        "base_flow": 4000.0,
                        "extra_release_rate": 0.25,
                    },
                }
            ],
        },
        {
            "name": "方案C: 蓄水量驱动(激进)",
            "modules": [
                {
                    "module_type": "storage_driven",
                    "parameters": {
                        "low_storage_threshold": 0.4,
                        "high_storage_threshold": 0.6,
                        "base_flow": 6000.0,
                        "extra_release_rate": 0.4,
                    },
                }
            ],
        },
    ]

    # ── 逐方案仿真+评估 ──────────────────────────────────────────
    results = []
    for i, cand in enumerate(candidates):
        program = ps.create_program(
            name=cand["name"],
            time_horizon=TimeHorizon(start=start, end=start + timedelta(hours=39), time_step=3600),
            module_configs=cand["modules"],
        )
        sim_result = sim_s.run_simulation(program, state, forecast)
        eval_result = ev_s.evaluate(sim_result, constraint_set=constraints)

        results.append(
            {
                "name": cand["name"],
                "program_id": program.id,
                "max_level": sim_result.max_level,
                "min_level": sim_result.min_level,
                "avg_outflow": sim_result.avg_outflow,
                "overall_score": eval_result.overall_score,
                "flood_score": eval_result.flood_control_score,
                "supply_score": eval_result.water_supply_score,
                "violations": len(eval_result.constraint_violations),
            }
        )

    # ── 比较输出 ─────────────────────────────────────────────────
    results.sort(key=lambda x: x["overall_score"], reverse=True)

    print(
        f"\n{'方案':<30} {'综合分':<10} {'防洪分':<10} {'供水分':<10} "
        f"{'最高水位':<10} {'最低水位':<10} {'平均出流':<10} {'违反':<6}"
    )
    print("-" * 106)
    for r in results:
        print(
            f"{r['name']:<30} {r['overall_score']:<10.1f} {r['flood_score']:<10.1f} "
            f"{r['supply_score']:<10.1f} {r['max_level']:<10.2f} {r['min_level']:<10.2f} "
            f"{r['avg_outflow']:<10.0f} {r['violations']:<6}"
        )

    best = results[0]
    print(f"\n推荐方案: {best['name']} (综合评分={best['overall_score']:.1f})")

    print("\n" + "=" * 70)
    print("案例 2 完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
