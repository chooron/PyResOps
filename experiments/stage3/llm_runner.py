"""Stage 3 LLM runner: wraps TrueMcpSkillRunner for static/dynamic/rolling workflows."""

from __future__ import annotations

import uuid
from typing import Any

from experiments.data_adapters.real_events import RealEventDataAdapter
from experiments.paper_validation.mcp_skill_runner import TrueMcpSkillRunner
from experiments.stage1.checkpoints import compute_dynamic_checkpoints
from experiments.stage1.constraints import get_flood_limit
from experiments.stage2.workflows import RollingThresholds
from experiments.stage3.fail_closed_validator import validate_stage3_decision
from experiments.stage3.mcp_tools import build_stage3_scenario
from experiments.stage3.payload_schema import payload_to_stage3_row
from experiments.stage3.session_trace import SessionTraceLogger


def _new_session_id() -> str:
    return uuid.uuid4().hex[:16]


def _should_retain_dynamic(prev_result: dict[str, Any]) -> tuple[bool, str]:
    """Mirror Stage 2 DynamicWorkflow._should_retain logic on LLM result."""
    if prev_result.get("hard_violation"):
        return False, "prior_violation"
    terminal_dev = prev_result.get("terminal_deviation", 999.0)
    if isinstance(terminal_dev, (int, float)) and terminal_dev > 0.5:
        return False, "terminal_deviation_exceeded"
    return True, "plan_still_feasible"


def _rolling_trigger(
    offset_hours: int,
    level: float,
    inflow: float,
    predict: float,
    flood_limit: float,
    thresholds: RollingThresholds,
) -> tuple[bool, str]:
    t = thresholds
    abs_error = abs(inflow - predict)
    rel_error = abs_error / max(abs(predict), 1.0)

    if offset_hours == 0:
        return True, "initial"
    if abs_error >= t.absolute_error_trigger_m3s:
        return True, "absolute_forecast_error"
    if rel_error >= t.relative_error_trigger:
        return True, "relative_forecast_error"
    if level >= flood_limit - t.level_risk_margin_m:
        return True, "level_risk"
    if t.scheduled_interval_hours > 0 and offset_hours % t.scheduled_interval_hours == 0:
        return True, "scheduled_check"
    return False, "retain_plan"


class Stage3LlmRunner:
    """Execute Stage 3 LLM+MCP evaluation for static, dynamic, and rolling workflows."""

    def __init__(
        self,
        *,
        model_profile: str | None = "mimo_v25",
        config_path: str | None = None,
        paper_config: dict[str, Any] | None = None,
        data_root: str = "data",
        traces_dir: str = "experiments/results/stage3",
        session_id: str | None = None,
    ) -> None:
        self.model_profile = model_profile or "mimo_v25"
        self.session_id = session_id or _new_session_id()
        self.adapter = RealEventDataAdapter(data_root=data_root)
        self._runner = TrueMcpSkillRunner(
            model_profile=model_profile,
            config_path=config_path,
            paper_config=paper_config or {},
        )
        self._traces_dir = traces_dir
        self._trace_logger: SessionTraceLogger | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_static(self, event_id: str) -> dict[str, Any]:
        """One LLM call for a static full-horizon workflow."""
        scenario = build_stage3_scenario(
            event_id=event_id,
            workflow_type="static",
            adapter=self.adapter,
            workflow_stage="static",
            offset_hours=0,
            use_predict=False,
            operator_instruction="",
            replan_reason="initial",
        )
        raw = self._runner.run_scenario(scenario)
        vr = validate_stage3_decision(raw, "static", scenario)
        row = self._build_row(raw, vr, event_id, "static", "static", scenario)
        self._log_trace(event_id, "static", "static", raw, vr, scenario)
        return row

    def run_dynamic(self, event_id: str) -> list[dict[str, Any]]:
        """One LLM call per dynamic checkpoint (T0–T4)."""
        event = self.adapter.load_event(event_id)
        inflows = [r.inflow for r in event.records if r.inflow is not None]
        checkpoints = compute_dynamic_checkpoints(inflows, event.time_step_hours)

        results: list[dict[str, Any]] = []
        prev_row: dict[str, Any] | None = None

        for stage_num, cp_idx in enumerate(checkpoints):
            stage_label = f"T{stage_num}"
            offset_hours = cp_idx * event.time_step_hours

            if prev_row is not None:
                retain, reason = _should_retain_dynamic(prev_row)
                workflow_type = "dynamic_retain" if retain else "dynamic_replan"
                replan_reason = reason
            else:
                workflow_type = "dynamic_replan"
                replan_reason = "initial"

            scenario = build_stage3_scenario(
                event_id=event_id,
                workflow_type=workflow_type,
                adapter=self.adapter,
                workflow_stage=stage_label,
                offset_hours=offset_hours,
                use_predict=False,
                operator_instruction="",
                replan_reason=replan_reason,
            )
            raw = self._runner.run_scenario(scenario)
            vr = validate_stage3_decision(raw, workflow_type, scenario)
            row = self._build_row(raw, vr, event_id, workflow_type, stage_label, scenario)
            self._log_trace(event_id, workflow_type, stage_label, raw, vr, scenario)
            results.append(row)
            prev_row = row

        return results

    def run_rolling(
        self,
        event_id: str,
        llm_call_policy: str = "trigger_only",
        log_retain_steps: bool = True,
    ) -> list[dict[str, Any]]:
        """Rolling workflow with configurable LLM call policy.

        llm_call_policy:
          "trigger_only" — call LLM only on trigger steps; retain steps get a
                           deterministic row with llm_called=False.
          "dense"        — call LLM on every 3h step (original behaviour).
        log_retain_steps: when trigger_only, whether to include retain rows in output.
        """
        withpred_path = self.adapter.data_root / "withpred" / f"{event_id}.csv"
        event = self.adapter.load_predicted_event(withpred_path)
        if not event.has_prediction:
            raise ValueError(f"{event_id}: rolling workflow requires predict column")

        thresholds = RollingThresholds()
        results: list[dict[str, Any]] = []
        prev_row: dict[str, Any] | None = None

        for idx, record in enumerate(event.records):
            if record.inflow is None or record.predict is None or record.level is None:
                continue
            offset_hours = idx * event.time_step_hours
            if offset_hours % thresholds.check_interval_hours != 0:
                continue
            remaining = event.duration_hours - offset_hours
            if remaining < thresholds.min_remaining_horizon_hours:
                continue

            flood_limit = get_flood_limit(record.time.month, record.time.day)
            trigger, reason = _rolling_trigger(
                offset_hours=offset_hours,
                level=float(record.level),
                inflow=float(record.inflow),
                predict=float(record.predict),
                flood_limit=flood_limit,
                thresholds=thresholds,
            )
            stage_label = f"rolling_{offset_hours}h"
            workflow_type = "rolling_replan" if trigger else "rolling_retain"

            call_llm = trigger or (llm_call_policy == "dense")

            if call_llm:
                scenario = build_stage3_scenario(
                    event_id=event_id,
                    workflow_type=workflow_type,
                    adapter=self.adapter,
                    workflow_stage=stage_label,
                    offset_hours=offset_hours,
                    use_predict=True,
                    operator_instruction="",
                    replan_reason=reason,
                )
                raw = self._runner.run_scenario(scenario)
                vr = validate_stage3_decision(raw, workflow_type, scenario)
                row = self._build_row(raw, vr, event_id, workflow_type, stage_label, scenario)
                row["llm_called"] = True
                row["trigger_reason"] = reason
                self._log_trace(event_id, workflow_type, stage_label, raw, vr, scenario)
            else:
                # Deterministic retain row — no LLM call
                if not log_retain_steps:
                    continue
                row = _build_retain_row(
                    event_id=event_id,
                    workflow_stage=stage_label,
                    trigger_reason=reason,
                    prev_row=prev_row,
                    model_profile=self.model_profile,
                    session_id=self.session_id,
                )

            results.append(row)
            prev_row = row

        return results

    def close(self) -> None:
        if self._trace_logger is not None:
            self._trace_logger.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_row(
        self,
        raw: dict[str, Any],
        vr: Any,
        event_id: str,
        workflow_type: str,
        workflow_stage: str,
        scenario: dict[str, Any],
    ) -> dict[str, Any]:
        from experiments.paper_validation.schema import validate_structured_payload

        payload_json = raw.get("accepted_evidence_pair", {})
        if isinstance(payload_json, dict):
            payload_json = payload_json.get("final_payload", payload_json)
        decision, _ = validate_structured_payload(payload_json)

        trace = raw.get("llm_execution_trace") or {}
        return payload_to_stage3_row(
            decision=decision,
            trace=raw,
            validation_result=vr,
            event_id=event_id,
            workflow_type=workflow_type,
            workflow_stage=workflow_stage,
            model_profile=self.model_profile,
            session_id=self.session_id,
        )

    def _log_trace(
        self,
        event_id: str,
        workflow_type: str,
        workflow_stage: str,
        raw: dict[str, Any],
        vr: Any,
        scenario: dict[str, Any],
    ) -> None:
        if self._trace_logger is None:
            self._trace_logger = SessionTraceLogger(
                traces_dir=self._traces_dir,
                session_id=self.session_id,
            )
        self._trace_logger.log(
            event_id=event_id,
            workflow_type=workflow_type,
            workflow_stage=workflow_stage,
            model_profile=self.model_profile,
            raw_result=raw,
            validation_result=vr,
            stage_payload=scenario,
        )


def _build_retain_row(
    event_id: str,
    workflow_stage: str,
    trigger_reason: str,
    prev_row: dict[str, Any] | None,
    model_profile: str,
    session_id: str,
) -> dict[str, Any]:
    """Deterministic retain row — no LLM call, carries forward previous plan."""
    return {
        "session_id": session_id,
        "event_id": event_id,
        "scenario_type": "rolling_retain",
        "workflow_stage": workflow_stage,
        "model_profile": model_profile,
        "llm_called": False,
        "trigger_reason": trigger_reason,
        # Carry-forward acceptance: retain rows are always accepted (deterministic)
        "accepted": True,
        "tool_order_valid": True,
        "eval_ref_valid": True,
        "schema_valid": True,
        "hard_violation": False,
        "downstream_violation": False,
        "payload_valid": True,
        "missing_required_tool": False,
        "wrong_tool_order": False,
        "stale_eval_ref": False,
        "missing_eval_ref": False,
        "schema_error": None,
        "tool_call_error": False,
        "llm_output_parse_error": False,
        "failure_reason": None,
        "tool_call_count": 0,
        "tool_call_sequence": [],
        "protocol_adherence": True,
        "final_payload_valid": True,
        "reference_valid": True,
        "mcp_connect_success": False,
        "decision_type": "retain_carry_over",
        "safety_status": prev_row.get("safety_status") if prev_row else None,
        "instruction_status": prev_row.get("instruction_status") if prev_row else None,
        "evaluation_reference": prev_row.get("evaluation_reference") if prev_row else None,
        "selected_plan_id": prev_row.get("selected_plan_id") if prev_row else None,
    }
