"""Plugin base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..constraints import ConstraintRegistry
from ..metrics import MetricRegistry
from ..rules import RuleRegistry


class PluginBase(ABC):
    """插件基类 (Plugin Base Class)."""

    @abstractmethod
    def initialize(self) -> None:
        """初始化插件."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取插件名称."""
        pass


class ConstraintPluginBase(PluginBase):
    """Base class for constraint plugins."""

    @abstractmethod
    def register_constraints(self, registry: ConstraintRegistry) -> None:
        """Register custom constraints."""


class RulePluginBase(PluginBase):
    """Base class for rule plugins."""

    @abstractmethod
    def register_rules(self, registry: RuleRegistry) -> None:
        """Register custom rules."""


class MetricPluginBase(PluginBase):
    """Base class for metric plugins."""

    @abstractmethod
    def register_metrics(self, registry: MetricRegistry) -> None:
        """Register custom metrics."""
