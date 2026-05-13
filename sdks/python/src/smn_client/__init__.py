"""SMN Python SDK — typed client for the Secure Multi-agent Network API.

Usage:
    from smn_client import SMNClient

    client = SMNClient(api_key="smn_...")
    agent = client.agents.create(name="analyst", model="gpt-4o")
    task = client.tasks.create(agent_id=agent.id, input_text="Summarise Q4 report")

Async:
    from smn_client import AsyncSMNClient

    client = AsyncSMNClient(api_key="smn_...")
    agent = await client.agents.create(name="analyst", model="gpt-4o")
"""

from smn_client._client import AsyncSMNClient, SMNClient
from smn_client._errors import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    SMNError,
    ValidationError,
)
from smn_client._types import ListPage

__all__ = [
    "SMNClient",
    "AsyncSMNClient",
    "ListPage",
    "SMNError",
    "APIError",
    "AuthenticationError",
    "AuthorizationError",
    "BadRequestError",
    "NotFoundError",
    "RateLimitError",
    "ValidationError",
]

__version__ = "0.1.0"
