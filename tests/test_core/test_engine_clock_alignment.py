"""Regression tests for authoritative simulation clock alignment."""

from datetime import datetime, timedelta

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
