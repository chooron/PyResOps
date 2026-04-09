"""Built-in constraint evaluators and registry helper."""

from __future__ import annotations

from ..registry import ConstraintRegistry
from .downstream import DownstreamFlowLimitConstraint
from .ecology import EcologicalMinFlowConstraint
from .flow import FlowMaxConstraint, FlowMinConstraint, WaterSupplyConstraint
from .level import LevelMaxConstraint, LevelMinConstraint, LevelRangeConstraint
from .ramp import RampRateMaxConstraint


def register_builtin_constraints(registry: ConstraintRegistry) -> None:
    """Register all built-in constraint evaluators."""
    registry.register(LevelMaxConstraint.constraint_type, LevelMaxConstraint)
    registry.register(LevelMinConstraint.constraint_type, LevelMinConstraint)
    registry.register(LevelRangeConstraint.constraint_type, LevelRangeConstraint)
    registry.register(FlowMaxConstraint.constraint_type, FlowMaxConstraint)
    registry.register(FlowMinConstraint.constraint_type, FlowMinConstraint)
    registry.register(WaterSupplyConstraint.constraint_type, WaterSupplyConstraint)
    registry.register(RampRateMaxConstraint.constraint_type, RampRateMaxConstraint)
    registry.register(DownstreamFlowLimitConstraint.constraint_type, DownstreamFlowLimitConstraint)
    registry.register(EcologicalMinFlowConstraint.constraint_type, EcologicalMinFlowConstraint)
