from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


HardConstraintType = Literal[
    "level_min",
    "level_max",
    "flow_min",
    "flow_max",
    "discharge_capacity",
    "ecological_min_flow",
]
TaskConstraintType = Literal[
    "deadline_level_target",
    "deadline_flow_limit",
    "quantitative_requirement",
]
ObjectiveTermType = Literal["min_avg_release", "max_generation"]
FallbackTermType = Literal["min_terminal_level_deviation"]
ReportingRequirementType = Literal[
    "report_task_completion",
    "report_unmet_constraints",
    "report_solve_stage",
    "report_compile_warnings",
]
CompilerStatus = Literal["ok", "warning", "error"]
CompilerMessageCode = Literal[
    "unmapped_instruction_phrase",
    "missing_rule_numeric_constraint",
    "unsupported_objective_family",
    "conflicting_user_constraint_with_hard_rule",
]
SolveStage = Literal["feasible_stage", "closest_safe_stage"]
SolveOutcome = Literal[
    "feasible_solution_found",
    "closest_safe_solution_found",
    "no_safe_solution_found",
]


@dataclass(frozen=True)
class CompilerMessage:
    code: CompilerMessageCode
    message: str
    severity: Literal["warning", "error"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HardConstraint:
    id: str
    type: HardConstraintType
    parameters: dict[str, Any]
    source: Literal["scenario", "rules", "user_instruction"]
    overridable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskConstraint:
    id: str
    type: TaskConstraintType
    parameters: dict[str, Any]
    source: Literal["rules", "user_instruction"]
    report_mode: Literal["required"] = "required"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObjectiveTerm:
    id: str
    type: ObjectiveTermType
    weight: float
    source: Literal["user_instruction", "default_compiler_policy"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FallbackTerm:
    id: str
    type: FallbackTermType
    weight: float
    source: Literal["compiler_policy"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportingRequirement:
    id: str
    type: ReportingRequirementType

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompiledDispatchContract:
    scenario_id: str
    hard_constraints: list[HardConstraint] = field(default_factory=list)
    task_constraints: list[TaskConstraint] = field(default_factory=list)
    objective_terms: list[ObjectiveTerm] = field(default_factory=list)
    fallback_terms: list[FallbackTerm] = field(default_factory=list)
    reporting_requirements: list[ReportingRequirement] = field(default_factory=list)
    status: CompilerStatus = "ok"
    messages: list[CompilerMessage] = field(default_factory=list)
    normalized_rule_facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "hard_constraints": [item.to_dict() for item in self.hard_constraints],
            "task_constraints": [item.to_dict() for item in self.task_constraints],
            "objective_terms": [item.to_dict() for item in self.objective_terms],
            "fallback_terms": [item.to_dict() for item in self.fallback_terms],
            "reporting_requirements": [item.to_dict() for item in self.reporting_requirements],
            "status": self.status,
            "messages": [item.to_dict() for item in self.messages],
            "normalized_rule_facts": dict(self.normalized_rule_facts),
        }


@dataclass(frozen=True)
class SolveCandidate:
    outflow_m3s: float
    final_level_m: float
    overall_score: float
    power_generation_score: float
    constraint_violations_count: int
    hard_constraint_violations: list[dict[str, Any]]
    meets_task_constraints: bool
    unmet_task_constraints: list[dict[str, Any]]
    simulation_payload: dict[str, Any]
    evaluation_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkSolveResult:
    solve_stage: SolveStage
    outcome: SolveOutcome
    selected_candidate: SolveCandidate | None
    unmet_task_constraints: list[dict[str, Any]] = field(default_factory=list)
    feasible_solution_found: bool = False
    fallback_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "solve_stage": self.solve_stage,
            "outcome": self.outcome,
            "selected_candidate": (
                None if self.selected_candidate is None else self.selected_candidate.to_dict()
            ),
            "unmet_task_constraints": list(self.unmet_task_constraints),
            "feasible_solution_found": self.feasible_solution_found,
            "fallback_applied": self.fallback_applied,
        }
