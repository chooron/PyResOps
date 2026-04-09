"""Dynamic loader for constraint evaluator classes."""

from __future__ import annotations

import importlib

from .base import ConstraintEvaluator


def load_evaluator_class(path: str) -> type[ConstraintEvaluator]:
    """Load evaluator class from `pkg.module:ClassName` string."""
    if ":" not in path:
        raise ValueError(f"Invalid evaluator class path: {path}")

    module_name, class_name = path.split(":", maxsplit=1)
    module = importlib.import_module(module_name)
    class_obj = getattr(module, class_name, None)
    if class_obj is None:
        raise ValueError(f"Evaluator class not found: {path}")
    if not issubclass(class_obj, ConstraintEvaluator):
        raise ValueError(f"Evaluator class must inherit ConstraintEvaluator: {path}")
    return class_obj
