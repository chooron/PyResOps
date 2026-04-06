"""Engine edge-case and branch-coverage tests."""

from datetime import datetime

import pytest

from res_ops.core import SimulationEngine
from res_ops.domain.program import DispatchProgram, TimeHorizon, ModuleInstance, SwitchCondition
from res_ops.domain.forecast import ForecastBundle, ForecastSeries
from res_ops.modules import ConstantReleaseModule, InflowDrivenModule


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_program(**overrides):
    defaults = dict(
        id="edge_test",
        name="边界测试",
        time_horizon=TimeHorizon(
            start=datetime(2024, 7, 1, 0, 0, 0),
            end=datetime(2024, 7, 1, 3, 0, 0),
            time_step=3600,
        ),
        module_sequence=[
            ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000.0})
        ],
    )
    defaults.update(overrides)
    return DispatchProgram(**defaults)


def _make_forecast(timestamps, values):
    return ForecastBundle(
        forecast_time=datetime(2024, 7, 1, 0, 0, 0),
        series=[ForecastSeries(variable="inflow", timestamps=timestamps, values=values)],
    )


# ─── Missing forecast ─────────────────────────────────────────────────────────


class TestEngineMissingForecast:
    """无预报数据"""

    def test_no_inflow_series_raises(self, sample_reservoir_spec, sample_initial_state):
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program()
        # forecast without "inflow" series
        forecast = ForecastBundle(
            forecast_time=datetime(2024, 7, 1),
            series=[ForecastSeries(variable="rainfall", timestamps=[], values=[])],
        )
        with pytest.raises(ValueError, match="inflow"):
            engine.simulate(program, sample_initial_state, forecast, {})

    def test_empty_inflow_series(self, sample_reservoir_spec, sample_initial_state):
        """空入流序列: inflow_map 为空, 回退到 state.inflow"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program()
        forecast = _make_forecast([], [])
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}

        result = engine.simulate(program, sample_initial_state, forecast, modules)
        assert len(result.snapshots) > 0
        # 入流回退到 state.inflow = 8000
        assert result.snapshots[0].inflow == 8000.0


# ─── Empty module sequence ────────────────────────────────────────────────────


class TestEngineEmptyModules:
    """空模块序列"""

    def test_empty_module_sequence(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(module_sequence=[])
        result = engine.simulate(program, sample_initial_state, sample_forecast, {})

        # 空模块: outflow = inflow (入流等于出流)
        for snap in result.snapshots:
            assert snap.outflow == snap.inflow
            assert snap.active_module is None

    def test_module_type_not_in_modules_dict(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """模块类型在 modules 字典中不存在 -> 入流等于出流"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            module_sequence=[ModuleInstance(module_type="nonexistent", parameters={})]
        )
        # 不提供 "nonexistent" 模块实例
        result = engine.simulate(program, sample_initial_state, sample_forecast, {})
        for snap in result.snapshots:
            assert snap.outflow == snap.inflow


# ─── Inflow-map timestamp fallback ────────────────────────────────────────────


class TestEngineInflowFallback:
    """预报时间戳与仿真时间不匹配"""

    def test_timestamp_mismatch_fallback(self, sample_reservoir_spec, sample_initial_state):
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program()
        # 预报的时间戳与仿真时间完全错开
        wrong_timestamps = [datetime(2025, 1, 1, h, 0, 0) for h in range(4)]
        forecast = _make_forecast(wrong_timestamps, [9999.0] * 4)
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}

        result = engine.simulate(program, sample_initial_state, forecast, modules)
        # 所有步都回退到 state.inflow
        for snap in result.snapshots:
            assert snap.inflow == 8000.0  # sample_initial_state.inflow


# ─── Switch condition edge cases ──────────────────────────────────────────────


class TestEngineSwitchConditionEdges:
    """切换条件边界"""

    def test_inflow_threshold_above(self, sample_reservoir_spec, sample_initial_state):
        """入流阈值 above 方向"""
        engine = SimulationEngine(sample_reservoir_spec)
        ts = [datetime(2024, 7, 1, h, 0, 0) for h in range(4)]
        forecast = _make_forecast(ts, [5000, 5000, 15000, 15000])  # 第3步起入流超阈值

        program = _make_program(
            module_sequence=[
                ModuleInstance(module_type="constant_release", parameters={"target_flow": 3000.0}),
                ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 1.0}),
            ],
            switch_conditions=[
                SwitchCondition(
                    from_module="constant_release",
                    to_module="inflow_driven",
                    condition_type="inflow_threshold",
                    parameters={"threshold": 10000.0, "direction": "above"},
                )
            ],
        )
        modules = {
            "constant_release": ConstantReleaseModule({"target_flow": 3000.0}),
            "inflow_driven": InflowDrivenModule({"coefficient": 1.0}),
        }
        result = engine.simulate(program, sample_initial_state, forecast, modules)
        assert len(result.snapshots) == 4

    def test_inflow_threshold_below(self, sample_reservoir_spec, sample_initial_state):
        """入流阈值 below 方向"""
        engine = SimulationEngine(sample_reservoir_spec)
        ts = [datetime(2024, 7, 1, h, 0, 0) for h in range(4)]
        forecast = _make_forecast(ts, [15000, 15000, 5000, 5000])

        program = _make_program(
            module_sequence=[
                ModuleInstance(module_type="inflow_driven", parameters={"coefficient": 1.0}),
                ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000.0}),
            ],
            switch_conditions=[
                SwitchCondition(
                    from_module="inflow_driven",
                    to_module="constant_release",
                    condition_type="inflow_threshold",
                    parameters={"threshold": 10000.0, "direction": "below"},
                )
            ],
        )
        modules = {
            "inflow_driven": InflowDrivenModule({"coefficient": 1.0}),
            "constant_release": ConstantReleaseModule({"target_flow": 5000.0}),
        }
        result = engine.simulate(program, sample_initial_state, forecast, modules)
        assert len(result.snapshots) == 4

    def test_storage_threshold_above(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """库容阈值 above 方向"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            switch_conditions=[
                SwitchCondition(
                    from_module="constant_release",
                    to_module="constant_release",
                    condition_type="storage_threshold",
                    parameters={"threshold": 100.0, "direction": "above"},
                )
            ],
        )
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}
        result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
        assert len(result.snapshots) > 0  # 不触发切换

    def test_storage_threshold_below(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """库容阈值 below 方向 (当前库容30 < 阈值40 触发)"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            switch_conditions=[
                SwitchCondition(
                    from_module="constant_release",
                    to_module="constant_release",
                    condition_type="storage_threshold",
                    parameters={"threshold": 40.0, "direction": "below"},
                )
            ],
        )
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}
        result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
        assert len(result.snapshots) > 0

    def test_time_based_no_trigger_time(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """time_based 缺少 trigger_time -> 不触发"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            switch_conditions=[
                SwitchCondition(
                    from_module="constant_release",
                    to_module="constant_release",
                    condition_type="time_based",
                    parameters={},  # 缺少 trigger_time
                )
            ],
        )
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}
        result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
        assert len(result.snapshots) > 0

    def test_switch_condition_from_wrong_module(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """切换条件 from_module 不匹配当前模块 -> 不触发"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            module_sequence=[
                ModuleInstance(module_type="constant_release", parameters={"target_flow": 5000.0}),
            ],
            switch_conditions=[
                SwitchCondition(
                    from_module="inflow_driven",  # 与当前模块不同
                    to_module="constant_release",
                    condition_type="level_threshold",
                    parameters={"threshold": 0.0, "direction": "above"},
                )
            ],
        )
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}
        result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
        for snap in result.snapshots:
            assert snap.active_module == "constant_release"

    def test_unknown_switch_condition_type(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """未知切换条件类型 -> 不触发"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            switch_conditions=[
                SwitchCondition(
                    from_module="constant_release",
                    to_module="constant_release",
                    condition_type="unknown_type",
                    parameters={},
                )
            ],
        )
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}
        result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
        assert len(result.snapshots) > 0

    def test_level_threshold_below(
        self, sample_reservoir_spec, sample_initial_state, sample_forecast
    ):
        """水位阈值 below 方向"""
        engine = SimulationEngine(sample_reservoir_spec)
        program = _make_program(
            switch_conditions=[
                SwitchCondition(
                    from_module="constant_release",
                    to_module="constant_release",
                    condition_type="level_threshold",
                    parameters={"threshold": 170.0, "direction": "below"},
                )
            ],
        )
        modules = {"constant_release": ConstantReleaseModule({"target_flow": 5000.0})}
        result = engine.simulate(program, sample_initial_state, sample_forecast, modules)
        # 当前水位165 < 170, 应触发
        assert len(result.snapshots) > 0
