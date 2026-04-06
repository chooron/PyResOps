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
from .objective import ObjectiveSet, Objective
from .result import SimulationResult, EvaluationResult, StateSnapshot
from .release import SegmentedReleaseSchedule

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
    "ObjectiveSet",
    "Objective",
    "SimulationResult",
    "EvaluationResult",
    "StateSnapshot",
    "SegmentedReleaseSchedule",
]
