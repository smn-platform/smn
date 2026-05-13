"""Base connector interface.

All connectors implement this interface so they can be discovered,
configured, and monitored uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorConfig:
    """Configuration for a connector instance."""

    name: str
    connector_type: str
    params: dict[str, Any] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)


class BaseConnector(ABC):
    """Abstract base for all connectors."""

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._is_connected = False

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection. Raises on failure."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up resources."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the connector is healthy."""

    @abstractmethod
    async def execute(self, operation: str, **kwargs: Any) -> Any:
        """Execute an operation through this connector."""
