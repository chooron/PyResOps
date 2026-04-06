"""Tests for new operation modules: combined_driven, level_tracking, external_constraint."""

import pytest

from pyresops.modules import (
    CombinedDrivenModule,
    LevelTrackingModule,
    ExternalConstraintModule,
)


class TestCombinedDrivenModule:
    """联合驱动模块测试."""

    def test_info(self):
        info = CombinedDrivenModule.get_info()
        assert info.module_type == "combined_driven"
        assert info.name == "联合驱动"

    def test_low_storage(self, sample_reservoir_spec, sample_initial_state):
        """低库容时出流应偏低."""
        module = CombinedDrivenModule(
            parameters={
                "inflow_weight": 0.5,
                "storage_weight": 0.5,
                "base_flow": 5000.0,
                "low_storage_threshold": 0.9,  # 当前低于此阈值
                "high_storage_threshold": 0.95,
            }
        )
        outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
        assert outflow > 0
        # 入流分量8000, 库容分量很低, 加权应在两者之间
        assert outflow < 8000.0

    def test_high_storage(self, sample_reservoir_spec):
        """高库容时出流应偏高."""
        from pyresops.domain.reservoir import ReservoirState
        from datetime import datetime

        state = ReservoirState(
            timestamp=datetime(2024, 7, 1),
            level=175.0,
            storage=39.3,  # ~100% of total_capacity
            inflow=8000.0,
            outflow=8000.0,
        )
        module = CombinedDrivenModule(
            parameters={
                "low_storage_threshold": 0.3,
                "high_storage_threshold": 0.8,
                "base_flow": 5000.0,
            }
        )
        outflow = module.compute_outflow(state, sample_reservoir_spec, 8000.0)
        assert outflow > 5000.0

    def test_validation_weights(self):
        with pytest.raises(ValueError):
            CombinedDrivenModule(parameters={"inflow_weight": 0, "storage_weight": 0})


class TestLevelTrackingModule:
    """目标水位跟踪模块测试."""

    def test_info(self):
        info = LevelTrackingModule.get_info()
        assert info.module_type == "level_tracking"
        assert "target_level" in info.parameters_schema["required"]

    def test_above_target(self, sample_reservoir_spec, sample_initial_state):
        """当前水位高于目标 -> 应增大出流."""
        module = LevelTrackingModule(parameters={"target_level": 160.0, "kp": 500.0})
        outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
        # level_error = 165 - 160 = 5, adjustment = 500*5 = 2500
        assert outflow > 8000.0
        assert outflow == pytest.approx(10500.0)

    def test_below_target(self, sample_reservoir_spec, sample_initial_state):
        """当前水位低于目标 -> 应减小出流."""
        module = LevelTrackingModule(parameters={"target_level": 170.0, "kp": 500.0})
        outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
        # level_error = 165 - 170 = -5, adjustment = 500*(-5) = -2500
        assert outflow < 8000.0
        assert outflow == pytest.approx(5500.0)

    def test_min_max_outflow(self, sample_reservoir_spec, sample_initial_state):
        """出流应限制在 [min, max] 范围内."""
        module = LevelTrackingModule(
            parameters={
                "target_level": 180.0,
                "kp": 5000.0,
                "min_outflow": 3000.0,
                "max_outflow": 12000.0,
            }
        )
        outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
        assert 3000.0 <= outflow <= 12000.0

    def test_validation_requires_target(self):
        with pytest.raises(ValueError):
            LevelTrackingModule(parameters={})


class TestExternalConstraintModule:
    """外部约束响应模块测试."""

    def test_info(self):
        info = ExternalConstraintModule.get_info()
        assert info.module_type == "external_constraint"
        assert "downstream_limit" in info.parameters_schema["required"]

    def test_normal_operation(self, sample_reservoir_spec, sample_initial_state):
        """正常情况: 出流不超过下游约束."""
        module = ExternalConstraintModule(
            parameters={
                "downstream_limit": 10000.0,
                "default_outflow": 8000.0,
                "safety_margin": 0.9,
            }
        )
        outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 8000.0)
        assert outflow <= 10000.0 * 0.9
        assert outflow == pytest.approx(8000.0)

    def test_emergency(self, sample_reservoir_spec, sample_initial_state):
        """紧急情况: 入流远超安全约束 -> 按安全上限泄流."""
        module = ExternalConstraintModule(
            parameters={
                "downstream_limit": 10000.0,
                "default_outflow": 8000.0,
                "safety_margin": 0.9,
            }
        )
        outflow = module.compute_outflow(sample_initial_state, sample_reservoir_spec, 20000.0)
        assert outflow == pytest.approx(9000.0)  # 10000 * 0.9

    def test_validation(self):
        with pytest.raises(ValueError):
            ExternalConstraintModule(parameters={})
