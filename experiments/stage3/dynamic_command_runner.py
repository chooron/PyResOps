"""Stage 3 dynamic command-intervention LLM runner.

Evaluates whether the LLM can correctly handle operator commands issued
mid-event at specific checkpoints (T1, T2_peak) via MCP tools.

Acceptance gate:
  accepted = tool_order_valid AND eval_ref_valid AND schema_valid
             AND NOT hard_violation AND NOT downstream_violation
             AND command_handling_success

Matrix: 5 events x 4 command types x 2 checkpoints = 40 rows per model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.data_adapters.real_events import RealEventDataAdapter
import experiments.paper_validation.mcp_skill_runner as _mcp_runner_module
from experiments.paper_validation.mcp_skill_runner import TrueMcpSkillRunner
from experiments.stage1.dynamic_command_intervention import (
    SELECTED_EVENTS,
    COMMAND_TYPES,
    CHECKPOINT_LABELS,
    CheckpointState,
    CommandSpec,
    build_checkpoint_states,
    build_command,
)
from experiments.stage3.fail_closed_validator import ValidationResult, validate_stage3_decision
from experiments.stage3.mcp_tools import build_stage3_scenario
from experiments.stage3.payload_schema import payload_to_stage3_row
from experiments.stage3.session_trace import SessionTraceLogger
from pyresops.agents.specs import load_default_experiment_spec


_PROMPTS_DIR = Path(__file__).resolve().parent / "dynamic_command_prompts"


def _load_dynamic_command_instructions() -> str:
    system_file = _PROMPTS_DIR / "system_dynamic_command.md"
    contract_file = _PROMPTS_DIR / "workflow_contract_dynamic_command.md"
    parts = []
    for f in (system_file, contract_file):
        if f.exists():
            parts.append(f.read_text(encoding="utf-8"))
    schema = (
        "Return strict JSON only with ALL required fields: "
        "event_id, workflow (always 'dynamic_replan'), stage_id, method_level (always 'L4'), "
        "transport (always 'mcp_tools'), skill_name ('dynamic_command_intervention_skill'), "
        "decision_type, selected_plan_id, target_release_summary (empty dict if unavailable), "
        "safety_status ('safe'/'unsafe'/'unknown'), hard_constraint_violation, "
        "instruction_status, tool_chain_summary, mcp_tool_chain_summary, "
        "evaluation_reference, failure_reason, explanation, "
        "command_type, command_text, command_parameters, "
        "command_feasibility ('feasible'/'infeasible'), "
        "command_outcome ('executed'/'rejected_infeasible'/'rejected_unsafe'), "
        "command_handling_success (bool), feasible_execution_success (bool), "
        "infeasibility_reason (null or string), checkpoint_id, eval_ref_id. "
        "Evidence binding is mandatory: evaluation_reference and eval_ref_id must be "
        "copied exactly from the reference_id returned by evaluate_release_plan. "
        "Do not omit event_id, workflow, method_level, or transport."
    )
    parts.append(schema)
    return "\n\n".join(parts)


def _build_operator_instruction(command: CommandSpec, checkpoint_id: str) -> str:
    params_str = json.dumps(command.command_parameters)
    return (
        f"Checkpoint: {checkpoint_id}. "
        f"Command type: {command.command_type}. "
        f"Command: {command.command_text}. "
        f"Parameters: {params_str}. "
        f"Apply these constraints when calling optimize_release_plan."
    )


def _extract_command_fields(
    raw: dict[str, Any],
    command: CommandSpec,
    checkpoint_id: str,
) -> tuple[bool, bool, str, str, str | None]:
    """Extract command_handling_success, feasible_execution_success, feasibility, outcome, infeasibility_reason."""
    payload_json = raw.get("accepted_evidence_pair", {})
    if isinstance(payload_json, dict):
        payload_json = payload_json.get("final_payload", payload_json)

    if not isinstance(payload_json, dict):
        return False, False, "unknown", "error", "payload_parse_failed"

    # Primary: read from LLM payload
    command_handling_success = payload_json.get("command_handling_success")
    feasible_execution_success = payload_json.get("feasible_execution_success")
    command_feasibility = payload_json.get("command_feasibility", "unknown")
    command_outcome = payload_json.get("command_outcome", "unknown")
    infeasibility_reason = payload_json.get("infeasibility_reason")

    # Fallback: derive from decision_type and instruction_status
    decision_type = payload_json.get("decision_type", "")
    instruction_status = payload_json.get("instruction_status", "")

    if command_handling_success is None:
        if decision_type in ("accept",):
            command_handling_success = True
        elif decision_type in ("reject_infeasible",):
            # Correct rejection = success
            command_handling_success = True
        else:
            command_handling_success = instruction_status in ("satisfied", "infeasible")

    if feasible_execution_success is None:
        feasible_execution_success = (
            decision_type == "accept"
            and instruction_status == "satisfied"
        )

    if command_feasibility == "unknown":
        if decision_type == "reject_infeasible":
            command_feasibility = "infeasible"
        elif decision_type == "accept":
            command_feasibility = "feasible"

    if command_outcome == "unknown":
        if decision_type == "accept":
            command_outcome = "executed"
        elif decision_type == "reject_infeasible":
            command_outcome = "rejected_infeasible"

    return (
        bool(command_handling_success),
        bool(feasible_execution_success),
        str(command_feasibility),
        str(command_outcome),
        infeasibility_reason,
    )


def _validate_dynamic_command(
    raw: dict[str, Any],
    scenario: dict[str, Any],
    command: CommandSpec,
    checkpoint_id: str,
) -> tuple[ValidationResult, bool, bool, str, str, str | None]:
    """Run fail-closed validation plus command handling checks."""
    vr = validate_stage3_decision(raw, "dynamic_replan", scenario)

    (
        command_handling_success,
        feasible_execution_success,
        command_feasibility,
        command_outcome,
        infeasibility_reason,
    ) = _extract_command_fields(raw, command, checkpoint_id)

    # Extend acceptance gate with command_handling_success
    if vr.accepted and not command_handling_success:
        vr.accepted = False
        if not vr.failure_reason:
            vr.failure_reason = "command_handling_failed"

    return (
        vr,
        command_handling_success,
        feasible_execution_success,
        command_feasibility,
        command_outcome,
        infeasibility_reason,
    )


def _build_dynamic_command_row(
    raw: dict[str, Any],
    vr: ValidationResult,
    command_handling_success: bool,
    feasible_execution_success: bool,
    command_feasibility: str,
    command_outcome: str,
    infeasibility_reason: str | None,
    event_id: str,
    checkpoint_id: str,
    checkpoint_time: float,
    command: CommandSpec,
    model_profile: str,
    session_id: str,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    from experiments.paper_validation.schema import validate_structured_payload

    payload_json = raw.get("accepted_evidence_pair", {})
    if isinstance(payload_json, dict):
        payload_json = payload_json.get("final_payload", payload_json)
    decision, _ = validate_structured_payload(payload_json)

    row = payload_to_stage3_row(
        decision=decision,
        trace=raw,
        validation_result=vr,
        event_id=event_id,
        workflow_type="dynamic_replan",
        workflow_stage=checkpoint_id,
        model_profile=model_profile,
        session_id=session_id,
    )

    # Command-intervention specific fields
    row["checkpoint_id"] = checkpoint_id
    row["checkpoint_time"] = checkpoint_time
    row["command_type"] = command.command_type
    row["command_text"] = command.command_text
    row["command_parameters"] = json.dumps(command.command_parameters)
    row["command_feasibility"] = command_feasibility
    row["command_outcome"] = command_outcome
    row["command_handling_success"] = command_handling_success
    row["feasible_execution_success"] = feasible_execution_success
    row["infeasibility_reason"] = infeasibility_reason

    # Metric fields from raw result
    for metric_field in (
        "max_level", "max_release", "terminal_level", "terminal_deviation",
        "peak_inflow", "peak_release", "inflow_peak_attenuation_rate",
        "routing_max_flow_hecheng", "downstream_margin",
    ):
        row.setdefault(metric_field, raw.get(metric_field))

    # eval_ref_id
    if decision is not None:
        row["eval_ref_id"] = decision.evaluation_reference
    else:
        row["eval_ref_id"] = None

    return row


class DynamicCommandLlmRunner:
    """Execute Stage 3 LLM+MCP evaluation for dynamic command-intervention."""

    def __init__(
        self,
        *,
        model_profile: str | None = "mimo_v25",
        config_path: str | None = None,
        paper_config: dict[str, Any] | None = None,
        data_root: str = "data",
        traces_dir: str = "experiments/results/stage3_dynamic_command",
        session_id: str | None = None,
    ) -> None:
        import uuid
        self.model_profile = model_profile or "mimo_v25"
        self.session_id = session_id or uuid.uuid4().hex[:16]
        self.adapter = RealEventDataAdapter(data_root=data_root)
        self._spec = load_default_experiment_spec()
        self._runner = TrueMcpSkillRunner(
            model_profile=model_profile,
            config_path=config_path,
            paper_config=paper_config or {},
        )
        self._traces_dir = traces_dir
        self._trace_logger: SessionTraceLogger | None = None

    def run(
        self,
        event_id: str,
        checkpoint_id: str,
        command_type: str,
    ) -> dict[str, Any]:
        """Run one (event, checkpoint, command) LLM evaluation."""
        event = self.adapter.load_event(event_id)
        cp_states = build_checkpoint_states(event, self._spec)
        cp_state = next((s for s in cp_states if s.checkpoint_id == checkpoint_id), None)
        if cp_state is None:
            raise ValueError(f"Checkpoint {checkpoint_id!r} not found for event {event_id}")

        command = build_command(command_type, cp_state)
        operator_instruction = _build_operator_instruction(command, checkpoint_id)

        scenario = build_stage3_scenario(
            event_id=event_id,
            workflow_type="dynamic_replan",
            adapter=self.adapter,
            workflow_stage=checkpoint_id,
            offset_hours=int(cp_state.checkpoint_hour),
            use_predict=False,
            operator_instruction=operator_instruction,
            replan_reason="command_intervention",
        )

        orig_load_skill = _mcp_runner_module._load_skill_instructions
        orig_user_msg = _mcp_runner_module._mcp_skill_user_message
        instructions = _load_dynamic_command_instructions()

        _op_instr = operator_instruction
        _cp_id = checkpoint_id

        def _patched_load_skill(workflow: str, method_level: str) -> str:
            return instructions

        def _patched_user_msg(payload: dict, method_level: str, skill_name: str | None) -> str:
            base = orig_user_msg(payload, method_level, skill_name)
            header = (
                f"OPERATOR COMMAND (MANDATORY):\n"
                f"  checkpoint_id: {_cp_id}\n"
                f"  {_op_instr}\n"
                f"Apply the command constraints when calling optimize_release_plan. "
                f"Return strict JSON with all required fields including "
                f"command_type, command_handling_success, command_feasibility, "
                f"command_outcome, feasible_execution_success, checkpoint_id."
            )
            return f"{header}\n\n{base}"

        _mcp_runner_module._load_skill_instructions = _patched_load_skill
        _mcp_runner_module._mcp_skill_user_message = _patched_user_msg
        orig_skill_enabled = self._runner.skill_enabled
        self._runner.skill_enabled = True
        try:
            raw = self._runner.run_scenario(scenario)
        finally:
            _mcp_runner_module._load_skill_instructions = orig_load_skill
            _mcp_runner_module._mcp_skill_user_message = orig_user_msg
            self._runner.skill_enabled = orig_skill_enabled

        (
            vr,
            command_handling_success,
            feasible_execution_success,
            command_feasibility,
            command_outcome,
            infeasibility_reason,
        ) = _validate_dynamic_command(raw, scenario, command, checkpoint_id)

        row = _build_dynamic_command_row(
            raw=raw,
            vr=vr,
            command_handling_success=command_handling_success,
            feasible_execution_success=feasible_execution_success,
            command_feasibility=command_feasibility,
            command_outcome=command_outcome,
            infeasibility_reason=infeasibility_reason,
            event_id=event_id,
            checkpoint_id=checkpoint_id,
            checkpoint_time=cp_state.checkpoint_hour,
            command=command,
            model_profile=self.model_profile,
            session_id=self.session_id,
            scenario=scenario,
        )

        self._log_trace(event_id, checkpoint_id, command_type, raw, vr, scenario)
        return row

    def close(self) -> None:
        if self._trace_logger is not None:
            self._trace_logger.close()

    def _log_trace(
        self,
        event_id: str,
        checkpoint_id: str,
        command_type: str,
        raw: dict[str, Any],
        vr: ValidationResult,
        scenario: dict[str, Any],
    ) -> None:
        if self._trace_logger is None:
            self._trace_logger = SessionTraceLogger(
                traces_dir=self._traces_dir,
                session_id=self.session_id,
            )
        self._trace_logger.log(
            event_id=event_id,
            workflow_type=f"dynamic_command_{command_type}_{checkpoint_id}",
            workflow_stage=checkpoint_id,
            model_profile=self.model_profile,
            raw_result=raw,
            validation_result=vr,
            stage_payload=scenario,
        )
