"""Stage2Runner: orchestrates static/dynamic/rolling workflows for Stage 2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from experiments.data_adapters.real_events import RealEventDataAdapter
from experiments.stage2.workflows import (
    DynamicWorkflow,
    RollingThresholds,
    RollingWorkflow,
    StaticWorkflow,
)


class Stage2Runner:
    """Runs Stage 2 deterministic workflow experiments.

    Mirrors Stage1Runner's public API but routes through workflow classes
    (StaticWorkflow, DynamicWorkflow, RollingWorkflow) instead of calling
    OptimizationService directly.
    """

    def __init__(
        self,
        data_root: str | Path = "data",
        rolling_thresholds: dict[str, Any] | None = None,
    ) -> None:
        self.data_root = str(data_root)
        self.adapter = RealEventDataAdapter(data_root=data_root)
        t = rolling_thresholds or {}
        self.rolling_thresholds = RollingThresholds(
            relative_error_trigger=float(t.get("relative_error_trigger", 0.20)),
            absolute_error_trigger_m3s=float(t.get("absolute_error_trigger_m3s", 200.0)),
            level_risk_margin_m=float(t.get("level_risk_margin_m", 1.0)),
            scheduled_interval_hours=int(t.get("scheduled_interval_hours", 12)),
            check_interval_hours=int(t.get("check_interval_hours", 3)),
            min_remaining_horizon_hours=int(t.get("min_remaining_horizon_hours", 9)),
        )

    def run_static(self, event_id: str) -> dict[str, Any]:
        wf = StaticWorkflow(adapter=self.adapter)
        return wf.run(event_id)

    def run_dynamic(self, event_id: str) -> list[dict[str, Any]]:
        wf = DynamicWorkflow(adapter=self.adapter)
        return wf.run(event_id)

    def run_rolling(self, event_id: str) -> list[dict[str, Any]]:
        wf = RollingWorkflow(adapter=self.adapter, thresholds=self.rolling_thresholds)
        return wf.run(event_id)
