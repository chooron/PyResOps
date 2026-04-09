"""Metric evaluator protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..domain.constraint import ConstraintSet
from ..domain.reservoir import ReservoirSpec
from ..domain.result import SimulationResult


class MetricEvaluator(ABC):
    """Pluggable evaluator for one metric score.

    Minimal custom metric template:

    ```python
    from pyresops.metrics.base import MetricEvaluator


    class MyMetric(MetricEvaluator):
        metric_name = "my_metric"

        def evaluate(self, *, spec, result, constraint_set, proxy_options):
            return 100.0
    ```
    """

    metric_name: str = "metric"

    @abstractmethod
    def evaluate(
        self,
        *,
        spec: ReservoirSpec,
        result: SimulationResult,
        constraint_set: ConstraintSet | None,
        proxy_options: dict[str, Any],
    ) -> float:
        """Return score in 0-100 range."""
