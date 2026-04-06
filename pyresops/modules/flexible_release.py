"""Flexible segmented release operation module."""

from ..domain.module import ModuleInfo
from ..domain.release import SegmentedReleaseSchedule
from ..domain.reservoir import ReservoirSpec, ReservoirState
from .base import BaseOperationModule


class FlexibleReleaseModule(BaseOperationModule):
    """Segmented release module driven by schedule and step timestamp."""

    MODULE_TYPE = "flexible_release"
    MODULE_NAME = "分段下泄"
    MODULE_DESCRIPTION = "按时间分段执行优化下泄流量"

    def __init__(self, parameters: dict[str, object]):
        super().__init__(parameters)
        self._schedule: SegmentedReleaseSchedule | None = None

    def validate_parameters(self) -> None:
        """Validate required schedule fields at module level."""
        payload = self.parameters.get("schedule", self.parameters)
        if "control_interval_seconds" not in payload:
            raise ValueError("FlexibleReleaseModule requires 'control_interval_seconds'")
        if "release_values" not in payload:
            raise ValueError("FlexibleReleaseModule requires 'release_values'")

        release_values = payload.get("release_values", [])
        if any(float(value) < 0 for value in release_values):
            raise ValueError("release_values must be non-negative")

    def bind_schedule(self, schedule: SegmentedReleaseSchedule) -> None:
        """Bind validated canonical schedule from simulation context."""
        self._schedule = schedule

    def compute_outflow(
        self, state: ReservoirState, spec: ReservoirSpec, inflow_forecast: float
    ) -> float:
        """Return segment release value at current step timestamp."""
        if self._schedule is not None:
            return float(self._schedule.release_at(state.timestamp))

        payload = self.parameters.get("schedule", self.parameters)
        release_values = payload.get("release_values", [])
        if not release_values:
            raise ValueError("FlexibleReleaseModule has no release_values")
        return float(release_values[0])

    @classmethod
    def get_info(cls) -> ModuleInfo:
        """Module metadata."""
        return ModuleInfo(
            module_type=cls.MODULE_TYPE,
            name=cls.MODULE_NAME,
            description=cls.MODULE_DESCRIPTION,
            parameters_schema={
                "type": "object",
                "properties": {
                    "control_interval_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "分段控制间隔（秒）",
                    },
                    "release_values": {
                        "type": "array",
                        "items": {"type": "number", "minimum": 0},
                        "description": "各分段下泄流量（m3/s）",
                    },
                    "schedule": {
                        "type": "object",
                        "description": "兼容字段，与上层参数等价",
                    },
                },
                "required": ["control_interval_seconds", "release_values"],
            },
        )
