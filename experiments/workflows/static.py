"""Static real-data workflow contract and execution."""

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


class StaticRealDataWorkflow:
    """Known full observed flood process; one verified Agno dispatch run."""

    workflow_type = "static"

    def __init__(self, adapter: RealEventDataAdapter | None = None, runner=None):
        self.adapter = adapter or RealEventDataAdapter()
        self.runner = runner

    def contract(self) -> WorkflowContract:
        return WorkflowContract(
            workflow_type=self.workflow_type,
            description=(
                "The complete observed inflow process is known. The agent must use "
                "the fixed tool chain once to produce and verify a dispatch plan."
            ),
            fixed_inputs=[
                "time",
                "prcp",
                "level",
                "inflow",
                "outflow",
                "flood_limit_level",
                "target_level",
            ],
            tool_chain=list(STATIC_S01_CHAIN),
            state_update_rules=[
                "Use the first valid observed state as the initial reservoir state.",
                "Use the full real observed inflow series as the forecast horizon.",
                "Do not replace missing tool output with model-side guessed releases.",
            ],
            output_schema=dict(COMMON_OUTPUT_SCHEMA),
            failure_conditions=list(COMMON_FAILURE_CONDITIONS),
        )

    def prepare(self, event: str | FloodEventData) -> WorkflowExecutionResult:
        loaded = self.adapter.load_event(event) if not isinstance(event, FloodEventData) else event
        profile = (
            ReservoirPromptPack.STATIC_S01_CHAIN_PROFILE
            if loaded.event_id == "2024072617"
            else ReservoirPromptPack.STATIC_RESERVOIR_PROFILE
        )
        payload = self.adapter.to_payload(
            loaded,
            workflow_type=self.workflow_type,
            scenario_id=f"static_{loaded.event_id}",
            agent_workflow_profile=profile,
        )
        stage = WorkflowStage(
            stage_id="static_initial",
            offset_hours=0,
            payload=payload,
            replan_required=True,
            replan_reason="known_full_real_hydrograph",
        )
        return WorkflowExecutionResult(
            workflow_type=self.workflow_type,
            event_id=loaded.event_id,
            contract=self.contract(),
            stages=[stage],
            success=True,
            diagnostics={"contract_only": self.runner is None},
        )

    def run(self, event: str | FloodEventData) -> WorkflowExecutionResult:
        prepared = self.prepare(event)
        if self.runner is None:
            return prepared
        stage = prepared.stages[0]
        stage.payload["stage_id"] = stage.stage_id
        stage.payload["replan_reason"] = stage.replan_reason
        result = self.runner.run_scenario(stage.payload)
        return WorkflowExecutionResult(
            workflow_type=self.workflow_type,
            event_id=prepared.event_id,
            contract=prepared.contract,
            stages=prepared.stages,
            success=bool(result.get("success")),
            result=result,
            failure_reason=result.get("acceptance_failure_reason"),
            diagnostics={"contract_only": False},
        )
