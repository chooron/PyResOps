"""
使用案例 3: 持久化与事件日志

演示使用 SQLite Repository 存储调度方案、仿真结果,
以及通过事件日志记录调度决策过程 (为未来 CBR 案例检索做准备):
1. 保存方案与仿真结果
2. 记录关键事件 (预报接收、方案生成、人工修正、最终执行)
3. 查询事件历史
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
from res_ops.services import ProgramService, SimulationService, EvaluationService
from res_ops.storage import Repository


def main():
    print("=" * 70)
    print("使用案例 3: 持久化与事件日志")
    print("=" * 70)

    # ── 1. 初始化仓库 ────────────────────────────────────────────
    repo = Repository(db_path=":memory:")  # 生产环境使用文件路径
    print("\n[1] SQLite 仓库初始化完成")

    # ── 2. 水库与服务 ────────────────────────────────────────────
    spec = ReservoirSpec(
        id="persist_res",
        name="持久化水库",
        dead_level=150,
        normal_level=175,
        flood_limit_level=155,
        design_flood_level=178,
        check_flood_level=182,
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
    state = ReservoirState(
        timestamp=datetime(2024, 7, 20, 0, 0, 0),
        level=162.0,
        storage=26.0,
        inflow=5000.0,
        outflow=5000.0,
    )

    ps = ProgramService()
    sim_s = SimulationService(spec, ps.get_module_registry())
    ev_s = EvaluationService(spec)

    # ── 3. 事件: 接收预报 ────────────────────────────────────────
    repo.log_event(
        "forecast_received",
        reservoir_id="persist_res",
        description="收到气象局72h洪水预报",
        data={"forecast_hours": 72, "peak_flow": 18000, "peak_time": "2024-07-21T06:00:00"},
    )
    print("\n[3] 事件记录: 预报接收")

    # ── 4. 生成方案并保存 ────────────────────────────────────────
    start = datetime(2024, 7, 20, 0, 0, 0)
    program = ps.create_program(
        name="7月20日调度方案",
        time_horizon=TimeHorizon(start=start, end=start + timedelta(hours=23), time_step=3600),
        module_configs=[
            {
                "module_type": "storage_driven",
                "parameters": {
                    "low_storage_threshold": 0.35,
                    "high_storage_threshold": 0.75,
                    "base_flow": 5000,
                    "extra_release_rate": 0.3,
                },
            }
        ],
    )

    # 保存方案到仓库
    repo.save_program(
        program.id,
        {
            "program_id": program.id,
            "name": program.name,
            "created_at": program.created_at.isoformat(),
            "modules": [m.model_dump() for m in program.module_sequence],
        },
    )

    repo.log_event(
        "program_created",
        reservoir_id="persist_res",
        program_id=program.id,
        description="生成调度方案",
        data={"module_count": len(program.module_sequence)},
    )
    print(f"[4] 方案保存: {program.name} (ID={program.id})")

    # ── 5. 仿真并保存结果 ────────────────────────────────────────
    values = [5000 + 650 * i if i < 20 else 18000 - 650 * (i - 20) for i in range(24)]
    forecast = ForecastBundle(
        forecast_time=start,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[start + timedelta(hours=h) for h in range(24)],
                values=values,
            )
        ],
    )
    sim_result = sim_s.run_simulation(program, state, forecast)

    repo.save_simulation_result(
        program.id,
        {
            "program_id": program.id,
            "start_time": sim_result.start_time.isoformat(),
            "end_time": sim_result.end_time.isoformat(),
            "max_level": sim_result.max_level,
            "min_level": sim_result.min_level,
            "avg_outflow": sim_result.avg_outflow,
            "snapshot_count": len(sim_result.snapshots),
        },
    )

    repo.log_event(
        "simulation_completed",
        reservoir_id="persist_res",
        program_id=program.id,
        description="仿真完成",
        data={"max_level": sim_result.max_level, "min_level": sim_result.min_level},
    )
    print(f"[5] 仿真结果保存: 最高水位={sim_result.max_level:.2f}m")

    # ── 6. 人工修正事件 ──────────────────────────────────────────
    repo.log_event(
        "manual_override",
        reservoir_id="persist_res",
        program_id=program.id,
        description="调度员手动调整: 前6h出流+2000m³/s",
        data={
            "adjustment": {"hours": [0, 1, 2, 3, 4, 5], "delta_outflow": 2000},
            "reason": "下游河道清淤施工要求加大预泄",
        },
    )
    print("[6] 事件记录: 人工修正")

    # ── 7. 最终执行事件 ──────────────────────────────────────────
    repo.log_event(
        "execution_confirmed",
        reservoir_id="persist_res",
        program_id=program.id,
        description="调度方案确认执行",
        data={"approver": "张三", "confirmed_at": "2024-07-20T07:30:00"},
    )
    print("[7] 事件记录: 执行确认")

    # ── 8. 保存当前快照 ──────────────────────────────────────────
    repo.save_snapshot(
        "persist_res",
        {
            "timestamp": datetime.now().isoformat(),
            "level": 162.0,
            "storage": 26.0,
            "inflow": 5000.0,
            "outflow": 5000.0,
        },
    )
    print("[8] 快照保存")

    # ── 9. 查询历史 ──────────────────────────────────────────────
    print("\n[9] 事件历史查询:")

    all_events = repo.list_events()
    print(f"    总事件数: {len(all_events)}")
    for evt in all_events:
        print(f"    - [{evt['event_type']}] {evt['description']}")

    manual_events = repo.list_events(event_type="manual_override")
    print(f"\n    人工修正事件: {len(manual_events)}条")

    res_events = repo.list_events(reservoir_id="persist_res")
    print(f"    该水库事件: {len(res_events)}条")

    # ── 10. 查询已保存的方案列表 ─────────────────────────────────
    programs = repo.list_programs()
    print(f"\n[10] 已保存方案: {len(programs)}个")
    for p in programs:
        print(f"    - {p['name']} (ID={p['program_id']})")

    repo.close()
    print("\n" + "=" * 70)
    print("案例 3 完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
