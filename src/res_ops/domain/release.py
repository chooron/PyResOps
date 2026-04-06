"""Segmented release schedule domain model."""

from __future__ import annotations

from datetime import datetime
from math import floor
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SegmentedReleaseSchedule(BaseModel):
    """Canonical segmented release schedule for flood operations."""

    start: datetime = Field(description="Schedule anchor start time")
    end: datetime = Field(description="Schedule anchor end time")
    control_interval_seconds: int = Field(gt=0, description="Control interval in seconds")
    release_values: list[float] = Field(min_length=1, description="Release values by segment")
    min_release: float | None = Field(default=None, ge=0.0)
    max_release: float | None = Field(default=None, ge=0.0)

    @field_validator("release_values")
    @classmethod
    def _validate_release_values(cls, values: list[float]) -> list[float]:
        normalized = [float(v) for v in values]
        if any(v < 0 for v in normalized):
            raise ValueError("release_values must be non-negative")
        return normalized

    @model_validator(mode="after")
    def _validate_shape_and_bounds(self) -> "SegmentedReleaseSchedule":
        horizon_seconds_raw = (self.end - self.start).total_seconds()
        horizon_seconds = int(round(horizon_seconds_raw))
        if horizon_seconds <= 0:
            raise ValueError("end must be later than start")

        if abs(horizon_seconds_raw - horizon_seconds) > 1e-6:
            raise ValueError("horizon length must resolve to integer seconds")

        if horizon_seconds % self.control_interval_seconds != 0:
            raise ValueError("horizon length must be divisible by control_interval_seconds")

        expected_size = int(horizon_seconds // self.control_interval_seconds)
        if len(self.release_values) != expected_size:
            raise ValueError(
                f"release_values length must be {expected_size} for given horizon and control interval"
            )

        if (
            self.min_release is not None
            and self.max_release is not None
            and self.min_release > self.max_release
        ):
            raise ValueError("min_release cannot be greater than max_release")

        for value in self.release_values:
            if self.min_release is not None and value < self.min_release:
                raise ValueError("release value below min_release")
            if self.max_release is not None and value > self.max_release:
                raise ValueError("release value above max_release")

        return self

    @property
    def segment_count(self) -> int:
        """Number of release segments."""
        return len(self.release_values)

    def segment_index_at(self, timestamp: datetime) -> int:
        """Return segment index using floor + boundary clamp contract."""
        if self.segment_count == 1:
            return 0

        elapsed_seconds = (timestamp - self.start).total_seconds()
        raw_index = int(floor(elapsed_seconds / self.control_interval_seconds))
        return max(0, min(raw_index, self.segment_count - 1))

    def release_at(self, timestamp: datetime) -> float:
        """Return release value for a given timestamp."""
        return self.release_values[self.segment_index_at(timestamp)]

    @classmethod
    def from_module_parameters(
        cls,
        *,
        parameters: dict[str, Any],
        start: datetime,
        end: datetime,
        min_release: float | None = None,
        max_release: float | None = None,
    ) -> "SegmentedReleaseSchedule":
        """Build canonical schedule from module parameters."""
        payload = parameters.get("schedule", parameters)
        if "control_interval_seconds" not in payload or "release_values" not in payload:
            raise ValueError(
                "Flexible release parameters must include control_interval_seconds and release_values"
            )

        resolved_min = min_release if min_release is not None else payload.get("min_release")
        resolved_max = max_release if max_release is not None else payload.get("max_release")

        return cls(
            start=start,
            end=end,
            control_interval_seconds=int(payload["control_interval_seconds"]),
            release_values=list(payload["release_values"]),
            min_release=resolved_min,
            max_release=resolved_max,
        )

    def to_module_parameters(self) -> dict[str, Any]:
        """Serialize schedule for module-parameter compatibility."""
        payload: dict[str, Any] = {
            "control_interval_seconds": self.control_interval_seconds,
            "release_values": list(self.release_values),
            "schedule": {
                "control_interval_seconds": self.control_interval_seconds,
                "release_values": list(self.release_values),
            },
        }

        if self.min_release is not None:
            payload["min_release"] = self.min_release
            payload["schedule"]["min_release"] = self.min_release

        if self.max_release is not None:
            payload["max_release"] = self.max_release
            payload["schedule"]["max_release"] = self.max_release

        return payload
