"""Tests for flexible release module behavior and V1 guards."""

from datetime import datetime, timedelta

import pytest

from res_ops.domain.program import TimeHorizon
from res_ops.domain.release import SegmentedReleaseSchedule
from res_ops.modules import FlexibleReleaseModule
from res_ops.services import ProgramService


def _make_schedule() -> SegmentedReleaseSchedule:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=12)
    return SegmentedReleaseSchedule(
        start=start,
        end=end,
        control_interval_seconds=3 * 3600,
        release_values=[1000.0, 2000.0, 3000.0, 4000.0],
    )


def test_flexible_release_returns_segment_value(
    sample_reservoir_spec, sample_initial_state
) -> None:
    schedule = _make_schedule()
    module = FlexibleReleaseModule(schedule.to_module_parameters())
    module.bind_schedule(schedule)

    state = sample_initial_state.copy_with_update(timestamp=schedule.start + timedelta(hours=6))
    outflow = module.compute_outflow(state, sample_reservoir_spec, 8000.0)
    assert outflow == 3000.0


def test_flexible_release_clamps_before_and_after(
    sample_reservoir_spec, sample_initial_state
) -> None:
    schedule = _make_schedule()
    module = FlexibleReleaseModule(schedule.to_module_parameters())
    module.bind_schedule(schedule)

    before = sample_initial_state.copy_with_update(timestamp=schedule.start - timedelta(hours=1))
    after = sample_initial_state.copy_with_update(timestamp=schedule.end + timedelta(hours=1))

    assert module.compute_outflow(before, sample_reservoir_spec, 0.0) == 1000.0
    assert module.compute_outflow(after, sample_reservoir_spec, 0.0) == 4000.0


def test_flexible_release_supports_different_control_intervals(
    sample_reservoir_spec,
    sample_initial_state,
) -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=12)

    one_hour = SegmentedReleaseSchedule(
        start=start,
        end=end,
        control_interval_seconds=3600,
        release_values=[float(1000 + i) for i in range(12)],
    )
    three_hour = SegmentedReleaseSchedule(
        start=start,
        end=end,
        control_interval_seconds=3 * 3600,
        release_values=[1000.0, 2000.0, 3000.0, 4000.0],
    )

    module_1h = FlexibleReleaseModule(one_hour.to_module_parameters())
    module_1h.bind_schedule(one_hour)
    module_3h = FlexibleReleaseModule(three_hour.to_module_parameters())
    module_3h.bind_schedule(three_hour)

    check_time = start + timedelta(hours=4)
    state = sample_initial_state.copy_with_update(timestamp=check_time)
    assert module_1h.compute_outflow(state, sample_reservoir_spec, 0.0) == 1004.0
    assert module_3h.compute_outflow(state, sample_reservoir_spec, 0.0) == 2000.0


def test_program_service_rejects_multiple_flexible_modules() -> None:
    service = ProgramService()
    start = datetime(2024, 7, 1, 0, 0, 0)
    horizon = TimeHorizon(start=start, end=start + timedelta(hours=6), time_step=3600)
    params = {
        "control_interval_seconds": 3 * 3600,
        "release_values": [1000.0, 1000.0],
    }

    with pytest.raises(ValueError, match="at most one flexible_release"):
        service.create_program(
            name="bad",
            time_horizon=horizon,
            module_configs=[
                {"module_type": "flexible_release", "parameters": params},
                {"module_type": "flexible_release", "parameters": params},
            ],
        )


def test_program_service_rejects_flexible_with_switch_conditions() -> None:
    from res_ops.domain.program import SwitchCondition

    service = ProgramService()
    start = datetime(2024, 7, 1, 0, 0, 0)
    horizon = TimeHorizon(start=start, end=start + timedelta(hours=6), time_step=3600)

    with pytest.raises(ValueError, match="mixing flexible_release"):
        service.create_program(
            name="bad",
            time_horizon=horizon,
            module_configs=[
                {
                    "module_type": "flexible_release",
                    "parameters": {
                        "control_interval_seconds": 3 * 3600,
                        "release_values": [1000.0, 1000.0],
                    },
                }
            ],
            switch_conditions=[
                SwitchCondition(
                    from_module="flexible_release",
                    to_module="constant_release",
                    condition_type="time_based",
                    parameters={"trigger_time": "2024-07-01T01:00:00"},
                )
            ],
        )
