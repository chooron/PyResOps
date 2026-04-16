from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TypeAlias


@dataclass
class BaseResult:
    """Shared result fields across static, dynamic, and automated experiments."""

    scenario_id: str
    seed: int
    run_index: int
    llm_temperature: float
    proposed_outflow: float
    executed_outflow: float
    final_level: float
    peak_outflow: float
    constraint_violations: int
    dead_level_violations: int
    normal_level_violations: int
    ecological_violations: int
    overall_score: float
    flood_control_score: float
    water_supply_score: float
    power_generation_score: float
    ecological_score: float
    compliance_score: float
    task_completed: bool
    decision_time: float
    tool_call_count: int
    textual_explanation: str
    experiment_type: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class StaticResult(BaseResult):
    experiment_type: str = "static"


@dataclass
class DynamicResult(BaseResult):
    experiment_type: str = "dynamic"
    stage_id: str = ""
    instruction_complied: bool = False
    outflow_change_magnitude: float = 0.0
    strategy_oscillation: bool = False
    partial_credit_score: float = 0.0


@dataclass
class AutomatedResult(BaseResult):
    experiment_type: str = "automated"
    forecast_step: int = 0
    perturbation_seed: int = 0
    key_dimension_gain: float = 0.0
    switch_rate: float = 0.0
    strategy_oscillation_count: int = 0
    switch_occurred: bool = False
    switch_threshold: float = 0.10
    is_no_switch_baseline: bool = False
    is_heuristic_baseline: bool = False


@dataclass
class RollingControlResult:
    scenario_id: str
    deviation_id: str
    deviation_type: str
    controller_type: str
    total_constraint_violations: int
    max_level_exceedance: float
    has_critical_risk: bool
    key_dimension_scores: dict
    overall_score: float
    performance_degradation: float
    correction_count: int
    effective_correction_count: int
    effective_correction_rate: float
    recovery_steps: int
    forecast_steps: int = 0
    switch_occurred: bool = False
    is_heuristic_baseline: bool = False
    raw_eval_results: list[dict] | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        if payload.get("raw_eval_results") is None:
            payload["raw_eval_results"] = []
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


ExperimentResult: TypeAlias = StaticResult | DynamicResult | AutomatedResult
