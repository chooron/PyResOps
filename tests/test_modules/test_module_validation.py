"""Module parameter validation: negative values, missing, boundary."""

import pytest

from pyresops.modules import (
    ConstantReleaseModule,
    InflowDrivenModule,
    StorageDrivenModule,
    CombinedDrivenModule,
    LevelTrackingModule,
    ExternalConstraintModule,
)


class TestConstantReleaseValidation:
    def test_missing_target_flow(self):
        with pytest.raises(ValueError, match="target_flow"):
            ConstantReleaseModule(parameters={})

    def test_negative_target_flow(self):
        with pytest.raises(ValueError, match="non-negative"):
            ConstantReleaseModule(parameters={"target_flow": -100})

    def test_zero_target_flow_ok(self):
        m = ConstantReleaseModule(parameters={"target_flow": 0.0})
        assert (
            m.compute_outflow(
                __import__("pyresops.domain.reservoir", fromlist=["ReservoirState"]).ReservoirState(
                    timestamp=__import__("datetime").datetime(2024, 1, 1),
                    level=165,
                    storage=30,
                    inflow=8000,
                    outflow=8000,
                ),
                __import__("pyresops.domain.reservoir", fromlist=["ReservoirSpec"]).ReservoirSpec(
                    id="x",
                    name="x",
                    dead_level=150,
                    normal_level=175,
                    flood_limit_level=145,
                    design_flood_level=180,
                    check_flood_level=185,
                    total_capacity=39.3,
                    flood_capacity=22,
                    level_storage_curve=__import__(
                        "pyresops.domain.reservoir", fromlist=["LevelStorageCurve"]
                    ).LevelStorageCurve(
                        levels=[135, 185],
                        storages=[0, 51.6],
                    ),
                    discharge_capacity=__import__(
                        "pyresops.domain.reservoir", fromlist=["DischargeCapacity"]
                    ).DischargeCapacity(
                        levels=[135, 185],
                        max_discharges=[0, 30000],
                    ),
                ),
                8000.0,
            )
            == 0.0
        )


class TestInflowDrivenValidation:
    def test_negative_coefficient(self):
        with pytest.raises(ValueError, match="non-negative"):
            InflowDrivenModule(parameters={"coefficient": -1.0})

    def test_default_coefficient(self):
        m = InflowDrivenModule(parameters={})
        assert m.parameters["coefficient"] == 1.0


class TestStorageDrivenValidation:
    def test_missing_low_threshold(self):
        with pytest.raises(ValueError, match="low_storage_threshold"):
            StorageDrivenModule(parameters={"high_storage_threshold": 0.8, "base_flow": 5000})

    def test_missing_high_threshold(self):
        with pytest.raises(ValueError, match="high_storage_threshold"):
            StorageDrivenModule(parameters={"low_storage_threshold": 0.3, "base_flow": 5000})

    def test_missing_base_flow(self):
        with pytest.raises(ValueError, match="base_flow"):
            StorageDrivenModule(
                parameters={"low_storage_threshold": 0.3, "high_storage_threshold": 0.8}
            )


class TestCombinedDrivenValidation:
    def test_negative_inflow_weight(self):
        with pytest.raises(ValueError, match="non-negative"):
            CombinedDrivenModule(parameters={"inflow_weight": -1, "storage_weight": 1})

    def test_negative_storage_weight(self):
        with pytest.raises(ValueError, match="non-negative"):
            CombinedDrivenModule(parameters={"inflow_weight": 1, "storage_weight": -1})

    def test_both_weights_zero(self):
        with pytest.raises(ValueError, match="at least one"):
            CombinedDrivenModule(parameters={"inflow_weight": 0, "storage_weight": 0})

    def test_defaults(self):
        m = CombinedDrivenModule(parameters={})
        assert m.parameters["inflow_weight"] == 0.5
        assert m.parameters["storage_weight"] == 0.5


class TestLevelTrackingValidation:
    def test_missing_target_level(self):
        with pytest.raises(ValueError, match="target_level"):
            LevelTrackingModule(parameters={})

    def test_zero_kp(self):
        with pytest.raises(ValueError, match="positive"):
            LevelTrackingModule(parameters={"target_level": 165, "kp": 0})

    def test_negative_kp(self):
        with pytest.raises(ValueError, match="positive"):
            LevelTrackingModule(parameters={"target_level": 165, "kp": -100})

    def test_defaults(self):
        m = LevelTrackingModule(parameters={"target_level": 165})
        assert m.parameters["kp"] == 500.0
        assert m.parameters["min_outflow"] == 0.0
        assert m.parameters["max_outflow"] == 999999.0


class TestExternalConstraintValidation:
    def test_missing_downstream_limit(self):
        with pytest.raises(ValueError, match="downstream_limit"):
            ExternalConstraintModule(parameters={})

    def test_negative_downstream_limit(self):
        with pytest.raises(ValueError, match="non-negative"):
            ExternalConstraintModule(parameters={"downstream_limit": -100})

    def test_safety_margin_zero(self):
        with pytest.raises(ValueError, match="safety_margin"):
            ExternalConstraintModule(parameters={"downstream_limit": 10000, "safety_margin": 0})

    def test_safety_margin_above_one(self):
        with pytest.raises(ValueError, match="safety_margin"):
            ExternalConstraintModule(parameters={"downstream_limit": 10000, "safety_margin": 1.5})

    def test_safety_margin_exactly_one_ok(self):
        m = ExternalConstraintModule(parameters={"downstream_limit": 10000, "safety_margin": 1.0})
        assert m.parameters["safety_margin"] == 1.0

    def test_defaults(self):
        m = ExternalConstraintModule(parameters={"downstream_limit": 10000})
        assert m.parameters["default_outflow"] == 5000.0
        assert m.parameters["safety_margin"] == 0.9
