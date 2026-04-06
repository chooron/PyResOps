"""Extreme input tests: zero inflow, extreme inflow, boundary levels."""

from datetime import datetime

import pytest

from res_ops.core import SimulationEngine
from res_ops.domain.program import DispatchProgram, TimeHorizon, ModuleInstance
from res_ops.domain.forecast import ForecastBundle, ForecastSeries
from res_ops.modules import (
    ConstantReleaseModule,
    InflowDrivenModule,
    StorageDrivenModule,
    LevelTrackingModule,
)


def _spec():
    from res_ops.domain.reservoir import ReservoirSpec, LevelStorageCurve, DischargeCapacity

    return ReservoirSpec(
        id="extreme",
        name="极端测试",
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


def _state(level, inflow):
    from res_ops.domain.reservoir import ReservoirState

    spec = _spec()
    storage = spec.level_storage_curve.get_storage(level)
    return ReservoirState(
        timestamp=datetime(2024, 7, 1),
        level=level,
        storage=storage,
        inflow=inflow,
        outflow=inflow,
    )


def _forecast(values):
    ts = [datetime(2024, 7, 1, h, 0, 0) for h in range(len(values))]
    return ForecastBundle(
        forecast_time=datetime(2024, 7, 1),
        series=[ForecastSeries(variable="inflow", timestamps=ts, values=values)],
    )


class TestZeroInflow:
    """入流为 0"""

    def test_constant_release_zero_inflow(self):
        spec = _spec()
        engine = SimulationEngine(spec)
        state = _state(165.0, 0.0)
        program = DispatchProgram(
            id="zero",
            name="零入流",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 2, 0, 0), time_step=3600
            ),
            module_sequence=[
                ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000})
            ],
        )
        forecast = _forecast([0.0, 0.0, 0.0])
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000})}
        result = engine.simulate(program, state, forecast, modules)
        assert len(result.snapshots) == 3
        # 入流=0, 出流=5000, 库容下降
        assert result.min_level < 165.0

    def test_inflow_driven_zero_inflow(self):
        spec = _spec()
        engine = SimulationEngine(spec)
        state = _state(165.0, 0.0)
        program = DispatchProgram(
            id="zero2",
            name="零入流驱动",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 2, 0, 0), time_step=3600
            ),
            module_sequence=[
                ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 1.0})
            ],
        )
        forecast = _forecast([0.0, 0.0, 0.0])
        modules = {"inflow_driven": InflowDrivenModule({"coefficient": 1.0})}
        result = engine.simulate(program, state, forecast, modules)
        for snap in result.snapshots:
            assert snap.outflow == 0.0


class TestExtremeInflow:
    """极端大入流"""

    def test_extreme_inflow_clamped_by_capacity(self):
        spec = _spec()
        engine = SimulationEngine(spec)
        state = _state(165.0, 50000.0)
        program = DispatchProgram(
            id="extreme",
            name="极端入流",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 2, 0, 0), time_step=3600
            ),
            module_sequence=[
                ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 0.5})
            ],
        )
        forecast = _forecast([50000.0, 50000.0, 50000.0])
        modules = {"inflow_driven": InflowDrivenModule({"coefficient": 0.5})}
        result = engine.simulate(program, state, forecast, modules)
        # 水位不应超过校核洪水位太多 (库容截断)
        for snap in result.snapshots:
            assert snap.level <= spec.check_flood_level + 5  # 允许一定余量


class TestBoundaryLevels:
    """水位边界"""

    def test_at_dead_level(self):
        spec = _spec()
        engine = SimulationEngine(spec)
        state = _state(spec.dead_level, 5000.0)
        program = DispatchProgram(
            id="dead",
            name="死水位",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 1, 0, 0), time_step=3600
            ),
            module_sequence=[
                ModuleInstance(module_type="constant_release", parameters={"target_flow": 3000})
            ],
        )
        forecast = _forecast([5000.0, 5000.0])
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 3000})}
        result = engine.simulate(program, state, forecast, modules)
        assert len(result.snapshots) == 2

    def test_at_check_flood_level(self):
        spec = _spec()
        engine = SimulationEngine(spec)
        state = _state(spec.check_flood_level, 8000.0)
        program = DispatchProgram(
            id="check",
            name="校核洪水位",
            time_horizon=TimeHorizon(
                start=datetime(2024, 7, 1), end=datetime(2024, 7, 1, 1, 0, 0), time_step=3600
            ),
            module_sequence=[
                ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 1.0})
            ],
        )
        forecast = _forecast([8000.0, 8000.0])
        modules = {"inflow_driven": InflowDrivenModule({"coefficient": 1.0})}
        result = engine.simulate(program, state, forecast, modules)
        assert len(result.snapshots) == 2


class TestHydraulicsBoundary:
    """水力学边界"""

    def test_storage_clamped_to_min(self):
        from res_ops.core import HydraulicsCalculator

        spec = _spec()
        h = HydraulicsCalculator(spec)
        state = _state(145.0, 0.0)  # 最低曲线点, storage=10
        # 大量出流 → 库容降到最小以下
        next_state = h.water_balance_step(state, inflow=0.0, outflow=50000.0, dt=86400)
        min_storage = spec.level_storage_curve.storages[0]
        assert next_state.storage >= min_storage

    def test_storage_clamped_to_max(self):
        from res_ops.core import HydraulicsCalculator

        spec = _spec()
        h = HydraulicsCalculator(spec)
        state = _state(175.0, 0.0)  # storage=39.3
        # 大量入流 → 库容超过总库容
        next_state = h.water_balance_step(state, inflow=100000.0, outflow=0.0, dt=86400)
        assert next_state.storage <= spec.total_capacity

    def test_validate_outflow_at_boundary(self):
        from res_ops.core import HydraulicsCalculator

        spec = _spec()
        h = HydraulicsCalculator(spec)
        max_d = h.compute_max_discharge(165.0)
        is_valid, adjusted = h.validate_outflow(165.0, max_d)
        assert is_valid
        assert adjusted == pytest.approx(max_d)

    def test_validate_outflow_slightly_over(self):
        from res_ops.core import HydraulicsCalculator

        spec = _spec()
        h = HydraulicsCalculator(spec)
        max_d = h.compute_max_discharge(165.0)
        is_valid, adjusted = h.validate_outflow(165.0, max_d + 0.01)
        assert not is_valid
        assert adjusted == pytest.approx(max_d)


class TestStorageDrivenBoundaries:
    """蓄水量驱动模块库容边界"""

    def test_zero_storage_ratio(self):
        spec = _spec()
        from res_ops.domain.reservoir import ReservoirState

        state = ReservoirState(
            timestamp=datetime(2024, 7, 1),
            level=145.0,
            storage=0.01,
            inflow=8000,
            outflow=8000,
        )
        m = StorageDrivenModule(
            parameters={
                "low_storage_threshold": 0.3,
                "high_storage_threshold": 0.8,
                "base_flow": 3000,
            }
        )
        outflow = m.compute_outflow(state, spec, 8000.0)
        assert outflow == 3000.0  # 低于 low -> base_flow

    def test_full_storage_ratio(self):
        spec = _spec()
        from res_ops.domain.reservoir import ReservoirState

        state = ReservoirState(
            timestamp=datetime(2024, 7, 1),
            level=175.0,
            storage=39.3,
            inflow=8000,
            outflow=8000,
        )
        m = StorageDrivenModule(
            parameters={
                "low_storage_threshold": 0.3,
                "high_storage_threshold": 0.8,
                "base_flow": 3000,
            }
        )
        outflow = m.compute_outflow(state, spec, 8000.0)
        assert outflow > 8000  # 高水位 -> 加大下泄


class TestLevelTrackingBoundary:
    """目标水位跟踪边界"""

    def test_exact_target(self):
        spec = _spec()
        from res_ops.domain.reservoir import ReservoirState

        state = ReservoirState(
            timestamp=datetime(2024, 7, 1),
            level=165.0,
            storage=30.0,
            inflow=8000,
            outflow=8000,
        )
        m = LevelTrackingModule(parameters={"target_level": 165.0, "kp": 500.0})
        outflow = m.compute_outflow(state, spec, 8000.0)
        assert outflow == pytest.approx(8000.0)  # 无偏差 -> 出流=入流
