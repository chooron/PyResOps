"""Dynamic loader for rule evaluator classes."""

from __future__ import annotations

import importlib

from .base import RuleEvaluator


def load_rule_evaluator_class(path: str) -> type[RuleEvaluator]:
    """Load evaluator class from `pkg.module:ClassName` string."""
    if ":" not in path:
        raise ValueError(f"Invalid rule evaluator class path: {path}")

    module_name, class_name = path.split(":", maxsplit=1)
    module = importlib.import_module(module_name)
    class_obj = getattr(module, class_name, None)
    if class_obj is None:
        raise ValueError(f"Rule evaluator class not found: {path}")
    if not issubclass(class_obj, RuleEvaluator):
        raise ValueError(f"Rule evaluator must inherit RuleEvaluator: {path}")
    return class_obj
