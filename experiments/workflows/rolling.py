"""Rolling real-data workflow contract and replan trigger logic."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from experiments.data_adapters import FloodEventData, RealEventDataAdapter
from experiments.workflows.contracts import (
    COMMON_FAILURE_CONDITIONS,
    COMMON_OUTPUT_SCHEMA,
    STATIC_S01_CHAIN,
    WorkflowContract,
    WorkflowExecutionResult,
    WorkflowStage,
)
from pyresops.agents.prompts import ReservoirPromptPack


@dataclass(frozen=True)
class RollingThresholds:
    relative_error_trigger: float = 0.2
    absolute_error_trigger_m3s: float = 150.0
    high_level_margin_m: float = 0.5
    min_remaining_horizon_hours: int = 9
    check_interval_hours: int = 3
    scheduled_check_replan: bool = False

    def __post_init__(self) -> None:
        if self.check_interval_hours <= 0:
            raise ValueError("check_interval_hours must be positive")


class RollingRealDataWorkflow:
    """Predicted inflow drives planning; observed inflow advances state."""

    workflow_type = "rolling"

    def __init__(
        self,
        adapter: RealEventDataAdapter | None = None,
        runner=None,
        thresholds: RollingThresholds | None = None,
        manual_instruction_offsets: dict[int, str] | None = None,
        continue_on_stage_failure: bool = False,
    ):
        self.adapter = adapter or RealEventDataAdapter()
        self.runner = runner
        self.thresholds = thresholds or RollingThresholds()
        self.continue_on_stage_failure = continue_on_stage_failure
        self.manual_instruction_offsets = (
            {6: "Operator review at 6h."}
            if manual_instruction_offsets is None
            else dict(manual_instruction_offsets)
        )

    def contract(self) -> WorkflowContract:
        return WorkflowContract(
            workflow_type=self.workflow_type,
            description=(
                "Use real predicted inflow for planning and real observed inflow for "
                "state advancement. Recompute only when forecast error, level risk, "
                "or a manual instruction crosses the configured trigger."
            ),
            fixed_inputs=[
                "time",
                "prcp",
                "level",
                "inflow",
                "outflow",
                "predict",
                "rolling_thresholds",
            ],
            tool_chain=list(STATIC_S01_CHAIN),
            state_update_rules=[
                "At each 3h row, compare predict against observed inflow.",
                "Advance state from the real level/inflow/outflow row.",
                "Plan with predict when available; evaluate with observed inflow.",
            ],
            output_schema=dict(COMMON_OUTPUT_SCHEMA),
            failure_conditions=list(COMMON_FAILURE_CONDITIONS),
        )

    def prepare(self, event: str | FloodEventData | None = None) -> WorkflowExecutionResult:
        loaded = (
            self.adapter.load_predicted_event()
            if event is None
            else event
            if isinstance(event, FloodEventData)
            else self._load_event_argument(event)
        )
        if not loaded.has_prediction:
            raise ValueError(f"{loaded.event_id}: rolling workflow requires predict column")
        stages: list[WorkflowStage] = []
        for index, record in enumerate(loaded.records):
            if record.inflow is None or record.predict is None or record.level is None:
                continue
            offset = index * loaded.time_step_hours
            if offset % self.thresholds.check_interval_hours != 0:
                continue
            remaining_hours = loaded.duration_hours - offset
            if remaining_hours < self.thresholds.min_remaining_horizon_hours:
                continue
            required, reason = self._needs_replan(offset, record.level, record.inflow, record.predict)
            if not required:
                continue
            instruction = self.manual_instruction_offsets.get(offset, "")
            payload = self.adapter.to_payload(
                loaded,
                workflow_type=self.workflow_type,
                scenario_id=f"rolling_{loaded.event_id}_{offset}h",
                stage_offset_hours=offset,
                operator_instruction=instruction,
                agent_workflow_profile=ReservoirPromptPack.ROLLING_RESERVOIR_PROFILE,
            )
            stages.append(
                WorkflowStage(
                    stage_id=f"rolling_{offset}h",
                    offset_hours=offset,
                    payload=payload,
                    operator_instruction=instruction,
                    replan_required=True,
                    replan_reason=reason,
                )
            )
        return WorkflowExecutionResult(
            workflow_type=self.workflow_type,
            event_id=loaded.event_id,
            contract=self.contract(),
            stages=stages,
            success=bool(stages),
            failure_reason=None if stages else "no_rolling_replan_triggered",
            diagnostics={
                "contract_only": self.runner is None,
                "thresholds": self.thresholds.__dict__,
                "forecast_error_pattern": loaded.forecast_error_pattern,
            },
        )

    def _load_event_argument(self, event: str) -> FloodEventData:
        if not str(event).startswith("stress://"):
            return self.adapter.load_predicted_event(event)
        parsed = urlparse(str(event))
        event_id = parsed.netloc or parsed.path.lstrip("/")
        pattern = (parse_qs(parsed.query).get("pattern") or [""])[0]
        if not event_id or not pattern:
            raise ValueError(f"Invalid rolling stress URI: {event}")
        return self.adapter.load_forecast_error_event(event_id, pattern)

    def _needs_replan(
        self,
        offset_hours: int,
        level: float,
        inflow: float,
        predict: float,
    ) -> tuple[bool, str]:
        if offset_hours in self.manual_instruction_offsets:
            return True, "manual_instruction"
        absolute_error = abs(float(inflow) - float(predict))
        relative_error = absolute_error / max(abs(float(predict)), 1.0)
        if absolute_error >= self.thresholds.absolute_error_trigger_m3s:
            return True, "absolute_forecast_error"
        if relative_error >= self.thresholds.relative_error_trigger:
            return True, "relative_forecast_error"
        if level >= self.adapter.flood_limit_level - self.thresholds.high_level_margin_m:
            return True, "state_risk"
        if self.thresholds.scheduled_check_replan:
            return True, f"scheduled_{self.thresholds.check_interval_hours}h_check"
        return False, "retain_plan"

    def run(self, event: str | FloodEventData | None = None) -> WorkflowExecutionResult:
        prepared = self.prepare(event)
        if self.runner is None:
            return prepared
        stage_results: list[dict] = []
        failure_reason = None
        for stage in prepared.stages:
            stage.payload["stage_id"] = stage.stage_id
            stage.payload["replan_reason"] = stage.replan_reason
            result = self.runner.run_scenario(stage.payload)
            stage_results.append(result)
            if not result.get("success") and failure_reason is None:
                failure_reason = result.get("acceptance_failure_reason") or "stage_failed"
            if not result.get("success") and not self.continue_on_stage_failure:
                break
        return WorkflowExecutionResult(
            workflow_type=self.workflow_type,
            event_id=prepared.event_id,
            contract=prepared.contract,
            stages=prepared.stages,
            success=failure_reason is None,
            result={"stage_results": stage_results},
            failure_reason=failure_reason,
            diagnostics=prepared.diagnostics | {"contract_only": False},
        )
