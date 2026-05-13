"""Connectors package — base class and built-in integrations."""

from smn.connectors.base import BaseConnector, ConnectorConfig
from smn.connectors.database import DatabaseConnector
from smn.connectors.email import EmailConnector
from smn.connectors.storage import StorageConnector
from smn.connectors.webhook import WebhookConnector

__all__ = [
    "BaseConnector",
    "ConnectorConfig",
    "DatabaseConnector",
    "EmailConnector",
    "StorageConnector",
    "WebhookConnector",
]
