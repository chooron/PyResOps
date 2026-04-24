"""Loading helpers for execution plugins."""

from __future__ import annotations

from importlib import import_module

from .base import ExecutionPluginBase
from .registry import ExecutionPluginRegistry


class PluginLoader:
    """Load trusted execution plugins into a registry."""

    def __init__(self, registry: ExecutionPluginRegistry):
        self.registry = registry

    def register_instance(self, plugin: ExecutionPluginBase) -> None:
        """Register one already-instantiated plugin."""
        self.registry.register(plugin)

    def load_from_path(self, import_path: str) -> ExecutionPluginBase:
        """Load a plugin class from `package.module:ClassName`."""
        module_path, _, class_name = import_path.partition(":")
        if not module_path or not class_name:
            raise ValueError(f"Invalid plugin import path: {import_path}")
        module = import_module(module_path)
        class_obj = getattr(module, class_name, None)
        if class_obj is None:
            raise ValueError(f"Plugin class not found: {import_path}")
        instance = class_obj()
        if not isinstance(instance, ExecutionPluginBase):
            raise ValueError(f"Execution plugin must inherit ExecutionPluginBase: {import_path}")
        self.registry.register(instance)
        return instance
