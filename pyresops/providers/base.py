"""Provider plugin interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from .models import DataRequest, ProviderTarget


class ProviderPluginBase(ABC):
    """Base interface for typed data providers."""

    provider_name: ClassVar[str]
    target_type: ClassVar[ProviderTarget]
    supported_sources: ClassVar[tuple[str, ...]] = ()

    def can_provide(self, request: DataRequest) -> bool:
        """Return whether this provider can satisfy the request."""
        if request.target_type != self.target_type:
            return False
        if request.source_hint is None:
            return True
        return request.source_hint in self.supported_sources

    @abstractmethod
    def provide(self, request: DataRequest, resolver: "DataResolver") -> object:
        """Materialize the requested object."""


class DataResolver(ABC):
    """Protocol implemented by provider resolvers."""

    @abstractmethod
    def ensure(self, request: DataRequest) -> object:
        """Resolve one request into a concrete typed object."""
