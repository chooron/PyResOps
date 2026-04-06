"""Combined scenario tests: full workflow with constraints, multi-module switching, score accuracy."""

from datetime import datetime, timedelta

import pytest

from pyresops.core import SimulationEngine, ConstraintValidator
from pyresops.domain.reservoir import (
    ReservoirSpec,
    ReservoirState,
    LevelStorageCurve,
    DischargeCapacity,
)
from pyresops.domain.program import DispatchProgram, TimeHorizon, ModuleInstance, SwitchCondition
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.modules import (
    ConstantReleaseModule,
    InflowDrivenModule,
    StorageDrivenModule,
    LevelTrackingModule,
)
from pyresops.services import (
    SnapshotService,
    ProgramService,
    SimulationService,
    EvaluationService,
    ExplanationService,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def full_spec():
    return ReservoirSpec(
        id="scenario_res",
        name="场景测试水库",
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


@pytest.fixture
def flood_forecast():
    """模拟洪水过程: 先涨后退"""
    start = datetime(2024, 7, 1, 0, 0, 0)
    values = [8000 + 1500 * i if i < 16 else 32000 - 1500 * (i - 16) for i in range(32)]
    ts = [start + timedelta(hours=i) for i in range(32)]
    return ForecastBundle(
        forecast_time=start,
        series=[ForecastSeries(variable="inflow", timestamps=ts, values=values)],
    )


@pytest.fixture
def initial_state():
    return ReservoirState(
        timestamp=datetime(2024, 7, 1),
        level=160.0,
        storage=25.0,
        inflow=8000.0,
        outflow=8000.0,
    )


# ─── Scenario 1: Full workflow with constraints ───────────────────────────────


class TestFullWorkflowWithConstraints:
    """端到端: 生成方案 → 仿真 → 约束校核 → 评估 → 解释"""

    def test_complete_pipeline(self, full_spec, initial_state, flood_forecast):
        # 1. 初始化服务
        ss = SnapshotService()
        ps = ProgramService()
        sim_s = SimulationService(full_spec, ps.get_module_registry())
        ev_s = EvaluationService(full_spec)
        ex_s = ExplanationService()

        # 2. 创建快照
        state = ss.create_initial_snapshot("res1", full_spec, 160.0, 8000.0)

        # 3. 创建调度方案
        program = ps.create_program(
            name="洪水调度方案",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1),
                end=datetime(2024, 7, 1, 23, 0, 0),
                time_step=3600,
            ),
            module_configs=[
                {
                    "module_type": "storage_driven",
                    "parameters": {
                        "low_storage_threshold": 0.4,
                        "high_storage_threshold": 0.75,
                        "base_flow": 5000.0,
                        "extra_release_rate": 0.3,
                    },
                }
            ],
        )

        # 4. 运行仿真
        result = sim_s.run_simulation(program, state, flood_forecast)
        assert result.program_id == program.id
        assert len(result.snapshots) == 24

        # 5. 约束校核
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="lmax",
                    name="最高水位",
                    constraint_type="level_max",
                    parameters={"max_level": 175.0},
                ),
                Constraint(
                    id="fmax",
                    name="最大流量",
                    constraint_type="flow_max",
                    parameters={"max_flow": 25000.0},
                ),
                Constraint(
                    id="ws",
                    name="供水需求",
                    constraint_type="water_supply",
                    parameters={"demand": 5000.0},
                ),
            ]
        )
        validator = ConstraintValidator(cs)
        violations = validator.validate_simulation(result)

        # 6. 评估 (含逐步评分)
        eval_result = ev_s.evaluate(result, constraint_set=cs, include_step_scores=True)
        assert eval_result.overall_score >= 0
        assert len(eval_result.step_scores) == 24

        # 7. 解释
        explanation = ex_s.explain_program(program, result, eval_result)
        assert "summary" in explanation
        assert "simulation_summary" in explanation
        assert "evaluation_summary" in explanation
        assert len(explanation["module_sequence"]) == 1


# ─── Scenario 2: Multi-module switching simulation ────────────────────────────


class TestMultiModuleSwitching:
    """多模块切换: 预泄 → 拦洪 → 敞泄"""

    def test_three_phase_dispatch(self, full_spec, initial_state, flood_forecast):
        engine = SimulationEngine(full_spec)

        program = DispatchProgram(
            id="three_phase",
            name="三阶段调度",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1),
                end=datetime(2024, 7, 1, 23, 0, 0),
                time_step=3600,
            ),
            module_sequence=[
                ModuleInstance(module_type="constant_release", parameters={"target_flow": 6000.0}),
                ModuleInstance(
                    module_type="level_tracking", parameters={"target_level": 155.0, "kp": 800.0}
                ),
                ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 1.0}),
            ],
            switch_conditions=[
                # 入流超 20000 -> 拦洪 (跟踪汛限水位)
                SwitchCondition(
                    from_module="constant_release",
                    to_module="level_tracking",
                    condition_type="inflow_threshold",
                    parameters={"threshold": 20000.0, "direction": "above"},
                ),
                # 入流回落到 15000 以下 -> 敞泄
                SwitchCondition(
                    from_module="level_tracking",
                    to_module="inflow_driven",
                    condition_type="inflow_threshold",
                    parameters={"threshold": 15000.0, "direction": "below"},
                ),
            ],
        )

        modules = {
            "constant_release": ConstantReleaseModule({"target_flow": 6000.0}),
            "level_tracking": LevelTrackingModule({"target_level": 155.0, "kp": 800.0}),
            "inflow_driven": InflowDrivenModule({"coefficient": 1.0}),
        }

        result = engine.simulate(program, initial_state, flood_forecast, modules)

        # 验证发生了模块切换
        active_modules = [s.active_module for s in result.snapshots]
        unique_modules = set(active_modules)
        assert len(unique_modules) >= 2  # 至少切换过一次

        # 验证仿真结果合理
        assert result.max_level > initial_state.level
        assert len(result.snapshots) == 24


# ─── Scenario 3: Score accuracy verification ──────────────────────────────────


class TestScoreAccuracy:
    """评分计算准确性"""

    def test_perfect_flood_control(self, full_spec):
        """最高水位不超过汛限水位 -> 防洪分 100"""
        ev = EvaluationService(full_spec)
        from pyresops.domain.result import SimulationResult, StateSnapshot

        result = SimulationResult(
            program_id="perfect",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=150.0,
                    storage=15,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=150.0,  # < flood_limit_level=155
            min_level=150.0,
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result)
        assert eval_result.flood_control_score == 100.0

    def test_perfect_water_supply(self, full_spec):
        """最低水位 >= 正常蓄水位 -> 供水分 100"""
        ev = EvaluationService(full_spec)
        from pyresops.domain.result import SimulationResult, StateSnapshot

        result = SimulationResult(
            program_id="perfect",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=176.0,
                    storage=40,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=176.0,
            min_level=176.0,  # >= normal_level=175
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result)
        assert eval_result.water_supply_score == 100.0

    def test_step_score_monotonicity(self, full_spec):
        """水位越高, 风险分应越低"""
        ev = EvaluationService(full_spec)
        from pyresops.domain.result import SimulationResult, StateSnapshot

        snapshots = [
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, h),
                level=145 + h * 2,
                storage=10 + h,
                inflow=8000,
                outflow=8000,
            )
            for h in range(10)
        ]
        result = SimulationResult(
            program_id="mono",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1, 9, 0, 0),
            snapshots=snapshots,
            max_level=163.0,
            min_level=145.0,
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result, include_step_scores=True)
        scores = [s.risk_score for s in eval_result.step_scores]
        # 水位递增 -> 风险分应递减 (或持平)
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i - 1] + 0.01

    def test_constraint_score_with_violations(self, full_spec):
        """有违反的步 -> constraint_score < 100"""
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c", name="", constraint_type="level_max", parameters={"max_level": 155.0}
                ),
            ]
        )
        ev = EvaluationService(full_spec)
        from pyresops.domain.result import SimulationResult, StateSnapshot

        snapshots = [
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, 0),
                level=150.0,
                storage=15,
                inflow=8000,
                outflow=8000,
            ),
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, 1),
                level=160.0,
                storage=25,
                inflow=8000,
                outflow=8000,
            ),  # 违反
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, 2),
                level=150.0,
                storage=15,
                inflow=8000,
                outflow=8000,
            ),
        ]
        result = SimulationResult(
            program_id="cv",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1, 2, 0, 0),
            snapshots=snapshots,
            max_level=160.0,
            min_level=150.0,
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result, constraint_set=cs, include_step_scores=True)
        # 第2步有违反
        assert eval_result.step_scores[1].constraint_score < 100.0
        # 第1步无违反
        assert eval_result.step_scores[0].constraint_score == 100.0
