"""Tests for segmented release schedule domain model."""

from datetime import datetime, timedelta

import pytest

from pyresops.domain.release import SegmentedReleaseSchedule


def test_schedule_length_validation() -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=12)

    with pytest.raises(ValueError, match="release_values length"):
        SegmentedReleaseSchedule(
            start=start,
            end=end,
            control_interval_seconds=3 * 3600,
            release_values=[1000.0, 2000.0, 3000.0],
        )


def test_schedule_rejects_negative_flows() -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=6)

    with pytest.raises(ValueError, match="non-negative"):
        SegmentedReleaseSchedule(
            start=start,
            end=end,
            control_interval_seconds=3 * 3600,
            release_values=[1000.0, -500.0],
        )


def test_segment_index_boundary_rules() -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=12)
    schedule = SegmentedReleaseSchedule(
        start=start,
        end=end,
        control_interval_seconds=3 * 3600,
        release_values=[1000.0, 2000.0, 3000.0, 4000.0],
    )

    assert schedule.segment_index_at(start - timedelta(minutes=30)) == 0
    assert schedule.segment_index_at(start) == 0
    assert schedule.segment_index_at(start + timedelta(hours=2, minutes=59)) == 0
    assert schedule.segment_index_at(start + timedelta(hours=3)) == 1
    assert schedule.segment_index_at(start + timedelta(hours=6)) == 2
    assert schedule.segment_index_at(end) == 3
    assert schedule.segment_index_at(end + timedelta(hours=1)) == 3


def test_release_value_selection_matches_index() -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=6)
    schedule = SegmentedReleaseSchedule(
        start=start,
        end=end,
        control_interval_seconds=3 * 3600,
        release_values=[1100.0, 2200.0],
    )

    assert schedule.release_at(start + timedelta(minutes=10)) == 1100.0
    assert schedule.release_at(start + timedelta(hours=3)) == 2200.0


def test_schedule_round_trip_module_parameters() -> None:
    start = datetime(2024, 7, 1, 0, 0, 0)
    end = start + timedelta(hours=6)
    schedule = SegmentedReleaseSchedule(
        start=start,
        end=end,
        control_interval_seconds=3 * 3600,
        release_values=[1200.0, 2400.0],
        min_release=1000.0,
        max_release=5000.0,
    )

    params = schedule.to_module_parameters()
    restored = SegmentedReleaseSchedule.from_module_parameters(
        parameters=params,
        start=start,
        end=end,
    )

    assert restored.control_interval_seconds == schedule.control_interval_seconds
    assert restored.release_values == schedule.release_values
    assert restored.min_release == schedule.min_release
    assert restored.max_release == schedule.max_release
