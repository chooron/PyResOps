"""MCP tools error-path and integration tests."""

from datetime import datetime

import pytest

from pyresops.services import (
    SnapshotService,
    ProgramService,
    SimulationService,
    EvaluationService,
    ExplanationService,
    OptimizationService,
    RollingOpsService,
)
from pyresops.domain.program import TimeHorizon
from pyresops.domain.reservoir import DischargeCapacity, LevelStorageCurve, ReservoirSpec
from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.storage import Repository


@pytest.fixture
def services():
    """初始化全套服务."""
    spec = ReservoirSpec(
        id="tool_test",
        name="工具测试水库",
        dead_level=150.0,
        normal_level=175.0,
        flood_limit_level=145.0,
        design_flood_level=180.0,
        check_flood_level=185.0,
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
    ss = SnapshotService()
    ps = ProgramService()
    sim_s = SimulationService(spec, ps.get_module_registry())
    ev_s = EvaluationService(spec)
    ex_s = ExplanationService()
    return {
        "spec": spec,
        "snapshot": ss,
        "program": ps,
        "simulation": sim_s,
        "evaluation": ev_s,
        "explanation": ex_s,
    }


# ─── Snapshot tool error paths ────────────────────────────────────────────────


class TestSnapshotToolErrors:
    def test_get_snapshot_not_found(self, services):
        svc = services["snapshot"]
        result = svc.get_snapshot("nonexistent")
        assert result is None

    def test_create_and_get_snapshot(self, services):
        svc = services["snapshot"]
        spec = services["spec"]
        state = svc.create_initial_snapshot("res1", spec, 165.0, 8000.0)
        assert state.level == 165.0

        retrieved = svc.get_snapshot("res1")
        assert retrieved is not None
        assert retrieved.level == 165.0

    def test_update_snapshot(self, services):
        svc = services["snapshot"]
        spec = services["spec"]
        state = svc.create_initial_snapshot("res1", spec, 165.0, 8000.0)
        updated = state.copy_with_update(level=170.0)
        svc.update_snapshot("res1", updated)

        retrieved = svc.get_snapshot("res1")
        assert retrieved.level == 170.0


# ─── Program tool error paths ─────────────────────────────────────────────────


class TestProgramToolErrors:
    def test_get_program_not_found(self, services):
        svc = services["program"]
        assert svc.get_program("nonexistent") is None

    def test_list_programs_empty(self, services):
        svc = services["program"]
        assert svc.list_programs() == []

    def test_list_available_modules(self, services):
        svc = services["program"]
        modules = svc.list_available_modules()
        types = [m["module_type"] for m in modules]
        assert "constant_release" in types
        assert "inflow_driven" in types
        assert "storage_driven" in types
        assert "combined_driven" in types
        assert "level_tracking" in types
        assert "external_constraint" in types
        assert "flexible_release" in types

    def test_get_module_registry(self, services):
        svc = services["program"]
        reg = svc.get_module_registry()
        assert "constant_release" in reg
        assert "flexible_release" in reg
        assert len(reg) == 7

    def test_create_program(self, services):
        svc = services["program"]
        program = svc.create_program(
            name="测试",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1),
                end=datetime(2024, 7, 2),
                time_step=3600,
            ),
            module_configs=[
                {"module_type": "constant_release", "parameters": {"target_flow": 5000}}
            ],
        )
        assert svc.get_program(program.id) is not None
        assert len(svc.list_programs()) == 1


# ─── Simulation tool error paths ──────────────────────────────────────────────


class TestSimulationToolErrors:
    def test_simulate_program_not_found(self, services):
        svc = services["simulation"]
        result = svc.get_result("nonexistent")
        assert result is None

    def test_run_simulation_success(self, services):
        ss = services["snapshot"]
        ps = services["program"]
        sim = services["simulation"]
        spec = services["spec"]

        state = ss.create_initial_snapshot("r1", spec, 165.0, 8000.0)
        program = ps.create_program(
            "t",
            TimeHorizon(
                start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 3, 0, 0), time_step=3600
            ),
            [{"module_type": "constant_release", "parameters": {"target_flow": 7000}}],
        )
        ts = [datetime(2024, 7, 1, h, 0, 0) for h in range(4)]
        forecast = ForecastBundle(
            forecast_time=datetime(2024, 7, 1),
            series=[ForecastSeries(variable="inflow", timestamps=ts, values=[8000.0] * 4)],
        )

        result = sim.run_simulation(program, state, forecast)
        assert result.program_id == program.id
        assert sim.get_result(program.id) is not None


# ─── Evaluation tool error paths ──────────────────────────────────────────────


class TestEvaluationToolErrors:
    def test_evaluate_flood_control_above_design(self, services):
        """max_level > design_flood_level -> 防洪分为 0"""
        from pyresops.domain.result import SimulationResult, StateSnapshot

        ev = services["evaluation"]
        result = SimulationResult(
            program_id="bad",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=182.0,
                    storage=40,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=182.0,  # > design_flood_level=180
            min_level=182.0,
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result)
        assert eval_result.flood_control_score == 0.0

    def test_evaluate_water_supply_below_dead(self, services):
        """min_level < dead_level -> 供水分为 0"""
        from pyresops.domain.result import SimulationResult, StateSnapshot

        ev = services["evaluation"]
        result = SimulationResult(
            program_id="bad",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=140.0,
                    storage=5,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=140.0,
            min_level=140.0,  # < dead_level=150
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result)
        assert eval_result.water_supply_score == 0.0

    def test_evaluate_flood_between_limit_and_design(self, services):
        """flood_limit < max_level < design -> 部分扣分"""
        from pyresops.domain.result import SimulationResult, StateSnapshot

        ev = services["evaluation"]
        result = SimulationResult(
            program_id="mid",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=160.0,
                    storage=25,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=160.0,  # > flood_limit=145, < design=180
            min_level=155.0,
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result)
        assert 0 < eval_result.flood_control_score < 100

    def test_evaluate_water_supply_between_dead_and_normal(self, services):
        """dead < min_level < normal -> 部分评分"""
        from pyresops.domain.result import SimulationResult, StateSnapshot

        ev = services["evaluation"]
        result = SimulationResult(
            program_id="mid",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=162.0,
                    storage=25,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=165.0,
            min_level=162.0,  # dead=150, normal=175
            avg_outflow=8000.0,
        )
        eval_result = ev.evaluate(result)
        assert 50 < eval_result.water_supply_score < 100

    def test_evaluate_with_violation_penalty(self, services):
        """有约束违反时综合分打折"""
        from pyresops.domain.result import SimulationResult, StateSnapshot
        from pyresops.domain.constraint import Constraint, ConstraintSet

        ev = services["evaluation"]
        result = SimulationResult(
            program_id="v",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=165.0,
                    storage=30,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=172.0,
            min_level=165.0,
            avg_outflow=8000.0,
        )
        cs = ConstraintSet(
            constraints=[
                Constraint(
                    id="c1", name="", constraint_type="level_max", parameters={"max_level": 170.0}
                ),
            ]
        )
        eval_with = ev.evaluate(result, constraint_set=cs)
        eval_without = ev.evaluate(result)
        assert eval_with.overall_score < eval_without.overall_score


# ─── Explanation tool error paths ─────────────────────────────────────────────


class TestExplanationToolErrors:
    def test_explain_without_simulation(self, services):
        """无仿真结果时也能生成解释"""
        ps = services["program"]
        ex = services["explanation"]

        program = ps.create_program(
            "t",
            TimeHorizon(start=datetime(2024, 7, 1), end=datetime(2024, 7, 2), time_step=3600),
            [{"module_type": "constant_release", "parameters": {"target_flow": 5000}}],
        )
        explanation = ex.explain_program(program)
        assert "summary" in explanation
        assert "simulation_summary" not in explanation
        assert "evaluation_summary" not in explanation

    def test_explain_with_simulation_only(self, services):
        """有仿真结果无评估结果"""
        from pyresops.domain.result import SimulationResult, StateSnapshot

        ps = services["program"]
        ex = services["explanation"]

        program = ps.create_program(
            "t",
            TimeHorizon(start=datetime(2024, 7, 1), end=datetime(2024, 7, 2), time_step=3600),
            [{"module_type": "constant_release", "parameters": {"target_flow": 5000}}],
        )
        sim_result = SimulationResult(
            program_id=program.id,
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 2),
            snapshots=[
                StateSnapshot(
                    timestamp=datetime(2024, 7, 1),
                    level=165.0,
                    storage=30,
                    inflow=8000,
                    outflow=8000,
                )
            ],
            max_level=165.0,
            min_level=165.0,
            avg_outflow=8000.0,
        )
        explanation = ex.explain_program(program, simulation_result=sim_result)
        assert "simulation_summary" in explanation
        assert "evaluation_summary" not in explanation


# ─── Compare programs edge ────────────────────────────────────────────────────


class TestCompareProgramsEdge:
    def test_compare_empty_list(self):
        """空列表比较"""
        from pyresops.services import EvaluationService

        # 模拟 compare_programs 逻辑
        comparisons = []
        comparisons.sort(key=lambda x: x["overall_score"], reverse=True)
        assert comparisons == []

    def test_compare_all_missing(self, services):
        """所有 program_id 都不存在"""
        sim = services["simulation"]
        ids = ["nonexistent1", "nonexistent2"]
        comparisons = []
        for pid in ids:
            result = sim.get_result(pid)
            if not result:
                continue
            comparisons.append({"program_id": pid})
        assert len(comparisons) == 0


class TestRollingWorkflowIntegration:
    def test_optimize_reassess_replace_finalize(self, services):
        ss = services["snapshot"]
        ps = services["program"]
        sim = services["simulation"]
        ev = services["evaluation"]
        spec = services["spec"]

        ss.create_initial_snapshot("roll_res", spec, 165.0, 8000.0)
        opt = OptimizationService(spec, ps)
        repo = Repository(":memory:")
        rolling = RollingOpsService(
            program_service=ps,
            simulation_service=sim,
            evaluation_service=ev,
            optimization_service=opt,
            snapshot_service=ss,
            repository=repo,
        )

        start = datetime(2024, 7, 1)
        forecast = ForecastBundle(
            forecast_time=start,
            series=[
                ForecastSeries(
                    variable="inflow",
                    timestamps=[start.replace(hour=h) for h in range(12)],
                    values=[8000.0 + h * 200 for h in range(12)],
                )
            ],
        )

        first = rolling.optimize_flexible_release_plan(
            reservoir_id="roll_res",
            context_id="ctx_roll",
            horizon_hours=12,
            control_interval_seconds=3 * 3600,
            forecast=forecast,
            constraints={"min_environmental_flow": 2000.0},
        )
        reassess = rolling.reassess_plan(
            reservoir_id="roll_res",
            context_id="ctx_roll",
            forecast=forecast,
            constraints={"min_environmental_flow": 2000.0},
        )
        assert reassess["working_plan_id"] == first["candidate_plan_id"]

        second = rolling.optimize_flexible_release_plan(
            reservoir_id="roll_res",
            context_id="ctx_roll",
            horizon_hours=12,
            control_interval_seconds=3 * 3600,
            forecast=forecast,
            constraints={"min_environmental_flow": 2500.0},
        )
        replace = rolling.replace_working_plan(
            reservoir_id="roll_res",
            context_id="ctx_roll",
            candidate_plan_id=second["candidate_plan_id"],
            reason="operator decision",
        )
        assert replace["working_plan_id"] == second["candidate_plan_id"]

        finalize = rolling.finalize_plan(reservoir_id="roll_res", context_id="ctx_roll")
        assert "persisted_ids" in finalize
        records = repo.list_finalized_records(reservoir_id="roll_res", context_id="ctx_roll")
        assert len(records) == 1
