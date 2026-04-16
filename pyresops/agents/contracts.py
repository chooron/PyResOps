from __future__ import annotations

from typing import NotRequired, Protocol, TypedDict


class ScenarioPayload(TypedDict):
    """Runtime input contract passed from callers to agent runtime."""

    id: str
    name: str
    description: str
    flood_limit_level: NotRequired[float]
    current_level: float
    initial_storage: float
    initial_inflow: float
    inflow: float
    target_level: float
    season: str
    flood_risk: str
    duration_hours: int
    time_step_hours: int
    temperature_override: NotRequired[float]
    llm_seed: NotRequired[int]
    reproducibility: NotRequired[dict]


class ScenarioRunResult(TypedDict):
    """Normalized runtime output contract consumed by experiments."""

    scenario_id: str
    method: str
    model: str
    outflow: float
    reasoning: str
    constraint_check: str
    parse_warning: str | None
    parsed_from: str
    llm_temperature: float
    llm_seed: int | None
    final_decision_text: str
    tool_call_count: int
    tool_call_chain: list[str]
    tool_calls_detail: list[dict]
    llm_execution_trace: dict
    accepted_attempt_index: int | None
    acceptance_failure_reason: str | None
    accepted_evidence_pair: dict | None
    total_time_seconds: float
    success: bool


class ScenarioRunnerProtocol(Protocol):
    """Stable seam between experiments and extracted agent runtime."""

    def run_scenario(self, payload: ScenarioPayload) -> ScenarioRunResult: ...
