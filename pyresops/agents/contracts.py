"""Typed contracts for the Agno reservoir agent boundary."""

from __future__ import annotations

from typing import NotRequired, Protocol, TypedDict


class ScenarioPayload(TypedDict):
    """Runtime input contract passed from workflow adapters to the agent runtime."""

    id: str
    name: str
    description: str
    flood_limit_level: float
    current_level: float
    initial_storage: float
    initial_inflow: float
    inflow: float
    target_level: float
    season: str
    flood_risk: str
    duration_hours: int
    time_step_hours: int
    benchmark_inflow_series_m3s: list[float]
    benchmark_observed_outflow_series_m3s: NotRequired[list[float]]
    benchmark_precipitation_series_mm: NotRequired[list[float]]
    benchmark_predicted_inflow_series_m3s: NotRequired[list[float]]
    data_source: NotRequired[dict]
    start_time: NotRequired[object]
    initial_outflow: NotRequired[float]
    target_level_tolerance: NotRequired[float]
    ecological_min_flow: NotRequired[float]
    agent_workflow_profile: NotRequired[str]
    workflow_type: NotRequired[str]
    stage_offset_hours: NotRequired[int]
    user_instruction: NotRequired[str]
    operator_instruction: NotRequired[str]
    carry_over_plan: NotRequired[dict]
    temperature_override: NotRequired[float]
    llm_seed: NotRequired[int]
    reproducibility: NotRequired[dict]


class ScenarioRunResult(TypedDict):
    """Normalized runtime output contract consumed by real-data workflows."""

    scenario_id: str
    method: str
    model: str
    success: bool
    process_success: NotRequired[bool]
    outflow: float | None
    final_decision_text: str
    tool_call_count: int
    tool_call_chain: list[str]
    tool_calls_detail: list[dict]
    llm_execution_trace: dict
    accepted_attempt_index: int | None
    acceptance_failure_reason: str | None
    accepted_evidence_pair: dict | None
    total_time_seconds: float
    reasoning: NotRequired[str]
    constraint_check: NotRequired[str]
    protocol_warning: NotRequired[str | None]
    safety_status: NotRequired[dict]
    instruction_status: NotRequired[dict]
    parse_warning: NotRequired[str | None]
    parsed_from: NotRequired[str]
    llm_temperature: NotRequired[float]
    llm_seed: NotRequired[int | None]
    llm_usage: NotRequired[dict | None]
    llm_usage_log_path: NotRequired[str | None]


class ScenarioRunnerProtocol(Protocol):
    """Stable boundary between workflow runners and the extracted agent runtime."""

    def run_scenario(self, payload: ScenarioPayload) -> ScenarioRunResult: ...
