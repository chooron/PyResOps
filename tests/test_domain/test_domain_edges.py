"""Domain object boundary and validation tests."""

import pytest

from pyresops.domain.reservoir import LevelStorageCurve, DischargeCapacity
from pyresops.domain.forecast import ForecastSeries, ForecastBundle
from pyresops.domain.constraint import Constraint, ConstraintSet
from pyresops.domain.objective import Objective, ObjectiveSet
from pyresops.domain.result import SimulationResult, StateSnapshot
from pyresops.domain.program import TimeHorizon
from datetime import datetime


# ─── LevelStorageCurve ────────────────────────────────────────────────────────


class TestLevelStorageCurve:
    def test_single_point(self):
        """单点曲线: 插值返回自身"""
        curve = LevelStorageCurve(levels=[100.0], storages=[0.0])
        assert curve.get_storage(100.0) == pytest.approx(0.0)
        assert curve.get_level(0.0) == pytest.approx(100.0)

    def test_extrapolation_below(self):
        """外插: 水位低于最低点"""
        curve = LevelStorageCurve(levels=[100.0, 110.0], storages=[0.0, 10.0])
        # np.interp 会钳位到端点
        assert curve.get_storage(90.0) == pytest.approx(0.0)

    def test_extrapolation_above(self):
        """外插: 水位高于最高点"""
        curve = LevelStorageCurve(levels=[100.0, 110.0], storages=[0.0, 10.0])
        assert curve.get_storage(120.0) == pytest.approx(10.0)

    def test_duplicate_levels_rejected(self):
        """非严格递增序列应报错"""
        with pytest.raises(ValueError):
            LevelStorageCurve(levels=[100.0, 100.0, 110.0], storages=[0.0, 5.0, 10.0])

    def test_decreasing_levels_rejected(self):
        with pytest.raises(ValueError):
            LevelStorageCurve(levels=[110.0, 100.0], storages=[0.0, 10.0])


# ─── DischargeCapacity ────────────────────────────────────────────────────────


class TestDischargeCapacity:
    def test_non_ascending_levels_rejected(self):
        with pytest.raises(ValueError):
            DischargeCapacity(levels=[110.0, 100.0], max_discharges=[1000.0, 500.0])

    def test_duplicate_levels_rejected(self):
        with pytest.raises(ValueError):
            DischargeCapacity(levels=[100.0, 100.0], max_discharges=[500.0, 1000.0])

    def test_interpolation(self):
        cap = DischargeCapacity(levels=[100.0, 120.0], max_discharges=[0.0, 10000.0])
        assert cap.get_max_discharge(110.0) == pytest.approx(5000.0)

    def test_extrapolation_clamped(self):
        cap = DischargeCapacity(levels=[100.0, 120.0], max_discharges=[0.0, 10000.0])
        assert cap.get_max_discharge(90.0) == pytest.approx(0.0)
        assert cap.get_max_discharge(130.0) == pytest.approx(10000.0)


# ─── ReservoirSpec ────────────────────────────────────────────────────────────


class TestReservoirSpecValidation:
    def test_level_at_dead(self, sample_reservoir_spec):
        assert sample_reservoir_spec.validate_level_range(sample_reservoir_spec.dead_level)

    def test_level_at_check_flood(self, sample_reservoir_spec):
        assert sample_reservoir_spec.validate_level_range(sample_reservoir_spec.check_flood_level)

    def test_level_below_dead(self, sample_reservoir_spec):
        assert not sample_reservoir_spec.validate_level_range(
            sample_reservoir_spec.dead_level - 1.0
        )

    def test_level_above_check_flood(self, sample_reservoir_spec):
        assert not sample_reservoir_spec.validate_level_range(
            sample_reservoir_spec.check_flood_level + 1.0
        )


# ─── Forecast ─────────────────────────────────────────────────────────────────


class TestForecastDomain:
    def test_series_to_dataframe(self):
        ts = [datetime(2024, 7, 1, h, 0, 0) for h in range(3)]
        series = ForecastSeries(variable="inflow", timestamps=ts, values=[100.0, 200.0, 300.0])
        df = series.to_dataframe()
        assert len(df) == 3
        assert "inflow" in df.columns

    def test_bundle_get_series_found(self):
        ts = [datetime(2024, 7, 1)]
        bundle = ForecastBundle(
            forecast_time=datetime(2024, 7, 1),
            series=[ForecastSeries(variable="inflow", timestamps=ts, values=[100.0])],
        )
        assert bundle.get_series("inflow") is not None

    def test_bundle_get_series_not_found(self):
        bundle = ForecastBundle(forecast_time=datetime(2024, 7, 1), series=[])
        assert bundle.get_series("inflow") is None

    def test_bundle_to_dataframe_empty(self):
        bundle = ForecastBundle(forecast_time=datetime(2024, 7, 1), series=[])
        df = bundle.to_dataframe()
        assert len(df) == 0

    def test_bundle_to_dataframe_multi_series(self):
        ts = [datetime(2024, 7, 1, h, 0, 0) for h in range(3)]
        bundle = ForecastBundle(
            forecast_time=datetime(2024, 7, 1),
            series=[
                ForecastSeries(variable="inflow", timestamps=ts, values=[1.0, 2.0, 3.0]),
                ForecastSeries(variable="rainfall", timestamps=ts, values=[10.0, 20.0, 30.0]),
            ],
        )
        df = bundle.to_dataframe()
        assert "inflow" in df.columns
        assert "rainfall" in df.columns


# ─── ConstraintSet ────────────────────────────────────────────────────────────


class TestConstraintSet:
    def test_add_constraint(self):
        cs = ConstraintSet()
        c = Constraint(
            id="c1", name="test", constraint_type="level_max", parameters={"max_level": 170}
        )
        cs.add_constraint(c)
        assert len(cs.constraints) == 1

    def test_get_by_type(self):
        cs = ConstraintSet(
            constraints=[
                Constraint(id="c1", name="", constraint_type="level_max", parameters={}),
                Constraint(id="c2", name="", constraint_type="flow_max", parameters={}),
                Constraint(id="c3", name="", constraint_type="level_max", parameters={}),
            ]
        )
        level_maxes = cs.get_by_type("level_max")
        assert len(level_maxes) == 2

    def test_get_by_type_empty(self):
        cs = ConstraintSet()
        assert cs.get_by_type("level_max") == []


# ─── Objective / ObjectiveSet ─────────────────────────────────────────────────


class TestObjective:
    def test_create_objective(self):
        obj = Objective(id="o1", name="防洪", objective_type="minimize_flood_risk", weight=0.6)
        assert obj.weight == 0.6

    def test_default_weight(self):
        obj = Objective(id="o1", name="", objective_type="minimize_flood_risk")
        assert obj.weight == 1.0

    def test_objective_set_add(self):
        oset = ObjectiveSet()
        oset.add_objective(Objective(id="o1", name="", objective_type="flood"))
        oset.add_objective(Objective(id="o2", name="", objective_type="supply"))
        assert len(oset.objectives) == 2

    def test_objective_set_get_by_type(self):
        oset = ObjectiveSet(
            objectives=[
                Objective(id="o1", name="", objective_type="flood"),
                Objective(id="o2", name="", objective_type="supply"),
                Objective(id="o3", name="", objective_type="flood"),
            ]
        )
        floods = oset.get_by_type("flood")
        assert len(floods) == 2

    def test_objective_set_get_by_type_empty(self):
        oset = ObjectiveSet()
        assert oset.get_by_type("any") == []


# ─── SimulationResult.to_dataframe ────────────────────────────────────────────


class TestSimulationResultMethods:
    def test_to_dataframe(self):
        snapshots = [
            StateSnapshot(
                timestamp=datetime(2024, 7, 1, h, 0, 0),
                level=165.0 + h,
                storage=30.0,
                inflow=8000.0,
                outflow=7000.0,
            )
            for h in range(3)
        ]
        result = SimulationResult(
            program_id="test",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1, 2, 0, 0),
            snapshots=snapshots,
            max_level=167.0,
            min_level=165.0,
            avg_outflow=7000.0,
        )
        df = result.to_dataframe()
        assert len(df) == 3
        assert "level" in df.columns
        assert "active_module" in df.columns

    def test_to_dataframe_empty(self):
        result = SimulationResult(
            program_id="test",
            start_time=datetime(2024, 7, 1),
            end_time=datetime(2024, 7, 1),
            snapshots=[],
            max_level=0,
            min_level=0,
            avg_outflow=0,
        )
        df = result.to_dataframe()
        assert len(df) == 0


# ─── TimeHorizon edge ─────────────────────────────────────────────────────────


class TestTimeHorizon:
    def test_zero_duration(self):
        h = TimeHorizon(
            start=datetime(2024, 7, 1),
            end=datetime(2024, 7, 1),
            time_step=3600,
        )
        assert h.total_steps() == 0

    def test_sub_hourly_step(self):
        h = TimeHorizon(
            start=datetime(2024, 7, 1),
            end=datetime(2024, 7, 1, 0, 30, 0),
            time_step=900,  # 15 min
        )
        assert h.total_steps() == 2
