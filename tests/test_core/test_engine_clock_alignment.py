"""Regression tests for authoritative simulation clock alignment."""

from datetime import datetime, timedelta

from experiments.baseline_human import HumanBaselineScheduler
from experiments.evaluation_metrics import _build_tankan_spec, _run_pyresops_eval
from pyresops.agents import ReservoirToolBundleFactory
from pyresops.core import resolve_scenario_start_time

from pyresops.domain.forecast import ForecastBundle, ForecastSeries
from pyresops.domain.program import DispatchProgram, ModuleInstance, TimeHorizon
from pyresops.modules import FlexibleReleaseModule
from pyresops.services import SimulationService, ProgramService


def test_flexible_release_uses_step_time_not_initial_timestamp(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    program_service = ProgramService()
    simulation_service = SimulationService(
        sample_reservoir_spec, program_service.get_module_registry()
    )

    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=6)
    horizon = TimeHorizon(start=start, end=end, time_step=3600)

    program = DispatchProgram(
        id="clock_align",
        name="clock_align",
        time_horizon=horizon,
        module_sequence=[
            ModuleInstance(
                module_type="flexible_release",
                parameters={
                    "control_interval_seconds": 3 * 3600,
                    "release_values": [1200.0, 3600.0],
                },
            )
        ],
        switch_conditions=[],
    )

    # Deliberately misaligned with time_horizon.start
    misaligned_state = sample_initial_state.copy_with_update(
        timestamp=start + timedelta(hours=5),
        level=160.0,
        inflow=5000.0,
        outflow=5000.0,
    )

    forecast = ForecastBundle(
        forecast_time=start,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[start + timedelta(hours=i) for i in range(7)],
                values=[6000.0] * 7,
            )
        ],
    )

    result = simulation_service.run_simulation(program, misaligned_state, forecast)

    assert result.snapshots[0].timestamp == start
    assert result.snapshots[0].outflow == 1200.0
    assert result.snapshots[2].outflow == 1200.0
    assert result.snapshots[3].outflow == 3600.0


def test_step_state_timestamp_tracks_current_time(
    sample_reservoir_spec, sample_initial_state
) -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    horizon = TimeHorizon(start=start, end=start + timedelta(hours=3), time_step=3600)
    program = DispatchProgram(
        id="clock_view",
        name="clock_view",
        time_horizon=horizon,
        module_sequence=[
            ModuleInstance(
                module_type="flexible_release",
                parameters={
                    "control_interval_seconds": 3600,
                    "release_values": [1000.0, 2000.0, 3000.0],
                },
            )
        ],
    )

    class RecorderModule(FlexibleReleaseModule):
        def __init__(self, parameters):
            super().__init__(parameters)
            self.seen_timestamps: list[datetime] = []

        def compute_outflow(self, state, spec, inflow_forecast):
            self.seen_timestamps.append(state.timestamp)
            return super().compute_outflow(state, spec, inflow_forecast)

    recorder = RecorderModule(program.module_sequence[0].parameters)
    from pyresops.domain.release import SegmentedReleaseSchedule

    schedule = SegmentedReleaseSchedule.from_module_parameters(
        parameters=program.module_sequence[0].parameters,
        start=start,
        end=horizon.end,
    )
    recorder.bind_schedule(schedule)

    forecast = ForecastBundle(
        forecast_time=start,
        series=[
            ForecastSeries(
                variable="inflow",
                timestamps=[start + timedelta(hours=i) for i in range(4)],
                values=[6000.0] * 4,
            )
        ],
    )

    from pyresops.core import SimulationEngine

    engine = SimulationEngine(sample_reservoir_spec)
    engine.simulate(
        program,
        sample_initial_state.copy_with_update(timestamp=start + timedelta(hours=2)),
        forecast,
        {"flexible_release": recorder},
    )

    assert recorder.seen_timestamps[0] == start
    assert recorder.seen_timestamps[1] == start + timedelta(hours=1)
    assert recorder.seen_timestamps[2] == start + timedelta(hours=2)


def test_resolve_scenario_start_time_shared_across_all_paths(monkeypatch) -> None:
    scenario = {
        "id": "S01",
        "name": "S01",
        "description": "clock alignment",
        "flood_limit_level": 156.5,
        "current_level": 157.5,
        "initial_storage": 33.1,
        "initial_inflow": 1000.0,
        "inflow": 1200.0,
        "target_level": 156.5,
        "season": "flood",
        "flood_risk": "high",
        "duration_hours": 24,
        "time_step_hours": 6,
        "scenario_start_time": "2026-01-02T03:00:00",
    }
    expected_start = resolve_scenario_start_time(scenario)

    captured: dict[str, datetime] = {}

    from experiments import evaluation_metrics as eval_module

    original_eval_resolver = eval_module.resolve_scenario_start_time

    def wrapped_eval_resolver(sc: dict):
        start = original_eval_resolver(sc)
        captured["evaluation_metrics"] = start
        return start

    monkeypatch.setattr(eval_module, "resolve_scenario_start_time", wrapped_eval_resolver)
    spec = _build_tankan_spec(flood_limit_level=scenario.get("flood_limit_level", 156.5))
    eval_result = _run_pyresops_eval(scenario, 1000.0, spec)
    assert eval_result["overall_score"] >= 0.0

    from experiments import baseline_human as human_module

    original_human_resolver = human_module.resolve_scenario_start_time

    def wrapped_human_resolver(sc: dict):
        start = original_human_resolver(sc)
        captured["human_baseline"] = start
        return start

    monkeypatch.setattr(human_module, "resolve_scenario_start_time", wrapped_human_resolver)
    human_scheduler = HumanBaselineScheduler()
    human_result = human_scheduler.schedule(scenario)
    assert human_result["overall_score"] >= 0.0

    agno_tools = __import__("types").SimpleNamespace(tool=lambda fn: fn)
    monkeypatch.setitem(__import__("sys").modules, "agno.tools", agno_tools)

    factory = ReservoirToolBundleFactory(
        scenario_resolver=lambda sid: scenario if sid == "S01" else None
    )
    tools = {tool.__name__: tool for tool in factory.make_tools(spec, runtime_scenario=scenario)}

    from pyresops.agents import tool_bundle as tool_bundle_module

    original_resolver = tool_bundle_module.resolve_tool_bundle_start_time
    call_order: list[datetime] = []

    def wrapped_resolver(sc: dict):
        start = original_resolver(sc)
        call_order.append(start)
        return start

    monkeypatch.setattr(tool_bundle_module, "resolve_tool_bundle_start_time", wrapped_resolver)

    tools["simulate_dispatch_program"]("S01", 1000.0, "constant_release")
    tools["evaluate_dispatch_result"]("S01", 1000.0)
    tools["optimize_release_plan"]("S01", horizon_hours=24)

    captured["tool_bundle_simulation"] = call_order[0]
    captured["tool_bundle_evaluation"] = call_order[1]
    captured["tool_bundle_optimization"] = call_order[2]

    assert captured["tool_bundle_simulation"] == expected_start
    assert captured["tool_bundle_evaluation"] == expected_start
    assert captured["tool_bundle_optimization"] == expected_start
    assert captured["evaluation_metrics"] == expected_start
    assert captured["human_baseline"] == expected_start
