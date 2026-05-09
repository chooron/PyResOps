"""Dynamic real-data workflow contract and stage construction."""

from __future__ import annotations

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


DEFAULT_DYNAMIC_INSTRUCTIONS = {
    3: "Operator tightens the target level after 3h; re-evaluate the plan.",
    6: "Operator requests stronger flood-control priority after 6h.",
    9: "Operator asks for updated release under the latest observed state after 9h.",
}
DEFAULT_DYNAMIC_TARGET_ADJUSTMENTS_M = {
    3: 0.0,
    6: -0.2,
    9: -0.1,
}


class DynamicRealDataWorkflow:
    """Observed process with manual instruction changes injected by stage."""

    workflow_type = "dynamic"

    def __init__(
        self,
        adapter: RealEventDataAdapter | None = None,
        runner=None,
        instructions: dict[int, str] | None = None,
        stage_offsets: list[int] | tuple[int, ...] | None = None,
        target_adjustments_m: dict[int, float] | None = None,
        target_level_tolerance: float = 0.1,
    ):
        self.adapter = adapter or RealEventDataAdapter()
        self.runner = runner
        if stage_offsets is None:
            self.instructions = dict(instructions or DEFAULT_DYNAMIC_INSTRUCTIONS)
        else:
            supplied = dict(instructions or {})
            self.instructions = {
                int(offset): supplied.get(
                    int(offset),
                    (
                        "Initial dispatch under the observed state."
                        if int(offset) == 0
                        else f"Operator update at {int(offset)}h; re-evaluate the plan."
                    ),
                )
                for offset in stage_offsets
            }
        self.target_adjustments_m = dict(
            target_adjustments_m or DEFAULT_DYNAMIC_TARGET_ADJUSTMENTS_M
        )
        self.target_level_tolerance = float(target_level_tolerance)

    def contract(self) -> WorkflowContract:
        return WorkflowContract(
            workflow_type=self.workflow_type,
            description=(
                "The complete observed process is known, but operator targets change "
                "at fixed 3h/6h/9h stages. Each stage starts from the observed real state."
            ),
            fixed_inputs=[
                "time",
                "prcp",
                "level",
                "inflow",
                "outflow",
                "stage_offset_hours",
                "operator_instruction",
                "carry_over_plan",
            ],
            tool_chain=[
                "initial: " + " -> ".join(STATIC_S01_CHAIN),
                "updated-retain: get_reservoir_status -> query_dispatch_rules -> simulate_dispatch_program -> evaluate_dispatch_result",
                "updated-replan: get_reservoir_status -> query_dispatch_rules -> simulate_dispatch_program -> evaluate_dispatch_result -> optimize_release_plan -> simulate_dispatch_program -> evaluate_dispatch_result",
            ],
            state_update_rules=[
                "At each injected offset, take level/inflow/outflow from the real CSV row.",
                "Use the remaining real observed inflow series as the stage horizon.",
                "Evaluate carry_over_plan before re-optimization when a prior plan exists.",
                "Hard reservoir safety constraints have priority over operator instruction targets.",
                "An unfinished instruction target is recorded as instruction_status=in_progress, not as workflow failure.",
            ],
            output_schema=dict(COMMON_OUTPUT_SCHEMA),
            failure_conditions=[
                *COMMON_FAILURE_CONDITIONS,
                "Only blocked execution, malformed outputs, missing tools, or untrustworthy tool results fail the workflow.",
                "Target-level non-compliance is evaluation status and may imply infeasible target adjustment, not process failure.",
            ],
        )

    def prepare(self, event: str | FloodEventData) -> WorkflowExecutionResult:
        loaded = self.adapter.load_event(event) if not isinstance(event, FloodEventData) else event
        stages: list[WorkflowStage] = []
        carry_over_plan: dict | None = None
        for offset in sorted(self.instructions):
            instruction = self.instructions[offset]
            payload = self.adapter.to_payload(
                loaded,
                workflow_type=self.workflow_type,
                scenario_id=f"dynamic_{loaded.event_id}_{offset}h",
                stage_offset_hours=offset,
                operator_instruction=instruction,
                carry_over_plan=carry_over_plan,
                target_level=self._target_level_for_offset(loaded, offset),
                target_level_tolerance=self.target_level_tolerance,
                agent_workflow_profile=ReservoirPromptPack.DYNAMIC_RESERVOIR_PROFILE,
            )
            stages.append(
                WorkflowStage(
                    stage_id=f"dynamic_{offset}h",
                    offset_hours=offset,
                    payload=payload,
                    operator_instruction=instruction,
                    replan_required=True,
                    replan_reason="operator_instruction_update",
                )
            )
            carry_over_plan = {
                "outflow": payload["initial_outflow"],
                "module_type": "constant_release",
                "module_parameters": {"target_release": payload["initial_outflow"]},
            }
        return WorkflowExecutionResult(
            workflow_type=self.workflow_type,
            event_id=loaded.event_id,
            contract=self.contract(),
            stages=stages,
            success=True,
            diagnostics={"contract_only": self.runner is None},
        )

    def run(self, event: str | FloodEventData) -> WorkflowExecutionResult:
        loaded = self.adapter.load_event(event) if not isinstance(event, FloodEventData) else event
        prepared = self.prepare(loaded)
        if self.runner is None:
            return prepared
        stages: list[WorkflowStage] = []
        stage_results: list[dict] = []
        failure_reason = None
        carry_over_plan: dict | None = None
        for offset in sorted(self.instructions):
            instruction = self.instructions[offset]
            payload = self.adapter.to_payload(
                loaded,
                workflow_type=self.workflow_type,
                scenario_id=f"dynamic_{loaded.event_id}_{offset}h",
                stage_offset_hours=offset,
                operator_instruction=instruction,
                carry_over_plan=carry_over_plan,
                target_level=self._target_level_for_offset(loaded, offset),
                target_level_tolerance=self.target_level_tolerance,
                agent_workflow_profile=ReservoirPromptPack.DYNAMIC_RESERVOIR_PROFILE,
            )
            stage = WorkflowStage(
                stage_id=f"dynamic_{offset}h",
                offset_hours=offset,
                payload=payload,
                operator_instruction=instruction,
                replan_required=True,
                replan_reason="operator_instruction_update",
            )
            stages.append(stage)
            stage.payload["stage_id"] = stage.stage_id
            stage.payload["replan_reason"] = stage.replan_reason
            result = self.runner.run_scenario(stage.payload)
            stage_results.append(result)
            if not result.get("success"):
                failure_reason = result.get("acceptance_failure_reason") or "stage_failed"
                break
            final_payload = (
                result.get("accepted_evidence_pair", {}).get("final_payload", {})
                if isinstance(result.get("accepted_evidence_pair"), dict)
                else {}
            )
            outflow = result.get("outflow")
            if outflow is not None:
                carry_over_plan = {
                    "outflow": float(outflow),
                    "module_type": final_payload.get("module_type", "constant_release"),
                    "module_parameters": final_payload.get(
                        "module_parameters",
                        {"target_release": float(outflow)},
                    ),
                }
        return WorkflowExecutionResult(
            workflow_type=self.workflow_type,
            event_id=prepared.event_id,
            contract=prepared.contract,
            stages=stages,
            success=failure_reason is None,
            result={"stage_results": stage_results},
            failure_reason=failure_reason,
            diagnostics={"contract_only": False},
        )

    def _target_level_for_offset(self, event: FloodEventData, offset_hours: int) -> float:
        sliced = event.slice_from_hour(offset_hours)
        first = sliced.records[sliced.first_valid_index()]
        if first.level is None:
            raise ValueError(f"{event.event_id}: missing level at dynamic offset {offset_hours}h")
        return float(first.level) + float(self.target_adjustments_m.get(offset_hours, 0.0))
