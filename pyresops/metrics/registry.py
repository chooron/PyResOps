"""Registry for metric evaluators."""

from __future__ import annotations

from collections.abc import Callable

from .base import MetricEvaluator

MetricFactory = Callable[[], MetricEvaluator]


class MetricRegistry:
    """Runtime registry for metric evaluator factories."""

    def __init__(self) -> None:
        self._factories: dict[str, MetricFactory] = {}

    def register(self, metric_name: str, factory: MetricFactory) -> None:
        """Register or replace metric evaluator by name."""
        self._factories[metric_name] = factory

    def create_all(self) -> dict[str, MetricEvaluator]:
        """Instantiate all registered metric evaluators."""
        return {name: factory() for name, factory in self._factories.items()}

    def list_metrics(self) -> list[str]:
        """Return sorted metric names."""
        return sorted(self._factories.keys())
