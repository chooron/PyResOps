"""Registry and resolver for provider plugins."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .base import DataResolver, ProviderPluginBase
from .models import DataRequest


class ProviderRegistry:
    """Registry for provider plugins grouped by target type."""

    def __init__(self) -> None:
        self._providers: dict[str, list[ProviderPluginBase]] = defaultdict(list)

    def register(self, provider: ProviderPluginBase) -> None:
        """Register one provider."""
        self._providers[provider.target_type].append(provider)

    def list(self, target_type: str | None = None) -> list[dict[str, Any]]:
        """List registered providers."""
        target_types = [target_type] if target_type else sorted(self._providers.keys())
        items: list[dict[str, Any]] = []
        for current in target_types:
            for provider in self._providers.get(current, []):
                items.append(
                    {
                        "provider_name": provider.provider_name,
                        "target_type": provider.target_type,
                        "supported_sources": list(provider.supported_sources),
                    }
                )
        return items


class ProviderManager(DataResolver):
    """Resolve typed data requests through registered providers."""

    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()

    def ensure(self, request: DataRequest) -> object:
        """Resolve one request."""
        providers = self.registry._providers.get(request.target_type, [])
        for provider in providers:
            if provider.can_provide(request):
                return provider.provide(request, self)
        available = [provider.provider_name for provider in providers]
        raise KeyError(
            f"No provider found for target_type='{request.target_type}' "
            f"source_hint='{request.source_hint}'. Available: {available or 'none'}"
        )

    @staticmethod
    def resolve_path(locator: str | None, *, base_dir: Path | None = None) -> Path:
        """Resolve a locator into an absolute path."""
        if locator is None:
            raise ValueError("Provider request requires a locator")
        path = Path(locator)
        if path.is_absolute():
            return path
        return (base_dir or Path.cwd()).joinpath(path).resolve()
