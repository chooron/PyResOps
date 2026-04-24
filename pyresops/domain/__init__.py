"""Domain objects for reservoir operation scheduling."""

from .reservoir import (
    ReservoirSpec,
    ReservoirState,
    LevelStorageCurve,
    DischargeCapacity,
)
from .forecast import ForecastBundle, ForecastSeries
from .program import DispatchProgram, ModuleInstance, SwitchCondition, TimeHorizon
from .module import OperationModule, ModuleInfo
from .constraint import ConstraintSet, Constraint
from .dispatch import (
    BenchmarkSolveResult,
    CompiledDispatchContract,
    CompilerMessage,
    FallbackTerm,
    HardConstraint,
    ObjectiveTerm,
    ReportingRequirement,
    SolveCandidate,
    TaskConstraint,
)
from .rule import RuleSet, DispatchRule, RuleAction
from .policy import PolicyBundle, ExecutionContext
from .decision import DecisionOutcome, DecisionTraceStep, ViolationRecord
from .objective import ObjectiveSet, Objective
from .result import SimulationResult, EvaluationResult, StateSnapshot

__all__ = [
    "ReservoirSpec",
    "ReservoirState",
    "LevelStorageCurve",
    "DischargeCapacity",
    "ForecastBundle",
    "ForecastSeries",
    "DispatchProgram",
    "ModuleInstance",
    "SwitchCondition",
    "TimeHorizon",
    "OperationModule",
    "ModuleInfo",
    "ConstraintSet",
    "Constraint",
    "CompilerMessage",
    "HardConstraint",
    "TaskConstraint",
    "ObjectiveTerm",
    "FallbackTerm",
    "ReportingRequirement",
    "CompiledDispatchContract",
    "SolveCandidate",
    "BenchmarkSolveResult",
    "RuleSet",
    "DispatchRule",
    "RuleAction",
    "PolicyBundle",
    "ExecutionContext",
    "DecisionOutcome",
    "DecisionTraceStep",
    "ViolationRecord",
    "ObjectiveSet",
    "Objective",
    "SimulationResult",
    "EvaluationResult",
    "StateSnapshot",
]
