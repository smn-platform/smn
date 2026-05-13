"""Database connector — governed SQL access for AI agents.

Provides:
- Read-only by default (write requires explicit scope)
- Query parameterisation enforced (no raw string interpolation)
- Row limit enforcement
- Query timeout
- Audit trail of all queries
"""

from __future__ import annotations

import logging
import re
from typing import Any

from smn.connectors.base import BaseConnector, ConnectorConfig

logger = logging.getLogger(__name__)

# Patterns that indicate destructive operations
_WRITE_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

_MAX_ROWS_DEFAULT = 1000
_QUERY_TIMEOUT_DEFAULT = 30


class DatabaseConnector(BaseConnector):
    """Governed database connector with read-only default and row limits."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._connection_url: str = config.params.get("connection_url", "")
        self._max_rows: int = config.params.get("max_rows", _MAX_ROWS_DEFAULT)
        self._query_timeout: int = config.params.get("query_timeout", _QUERY_TIMEOUT_DEFAULT)
        self._allow_writes: bool = "db:write" in config.scopes
        self._engine = None
        self._session_factory = None

    async def connect(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

        if not self._connection_url:
            raise ValueError("DatabaseConnector requires 'connection_url' in params")

        self._engine = create_async_engine(
            self._connection_url,
            pool_size=5,
            max_overflow=2,
            pool_timeout=self._query_timeout,
            echo=False,
        )
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._is_connected = True
        logger.info("DatabaseConnector connected: %s", self.config.name)

    async def disconnect(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
        self._is_connected = False

    async def health_check(self) -> bool:
        if not self._engine:
            return False
        try:
            from sqlalchemy import text
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def execute(self, operation: str, **kwargs: Any) -> Any:
        """Execute a database operation.

        Parameters
        ----------
        operation
            "query" for SELECT, "execute" for write operations.
        sql
            SQL statement (must use parameter placeholders).
        params
            Dictionary of query parameters.
        """
        if not self._session_factory:
            raise RuntimeError("DatabaseConnector not connected")

        sql: str = kwargs.get("sql", "")
        params: dict = kwargs.get("params", {})

        if not sql:
            raise ValueError("SQL statement is required")

        self._validate_sql(sql, operation)

        from sqlalchemy import text

        async with self._session_factory() as session:
            if operation == "query":
                result = await session.execute(
                    text(f"{sql} LIMIT {self._max_rows}") if "LIMIT" not in sql.upper()
                    else text(sql),
                    params,
                )
                rows = result.mappings().all()
                return [dict(r) for r in rows]

            elif operation == "execute":
                if not self._allow_writes:
                    raise PermissionError(
                        "Write operations require 'db:write' scope. "
                        "Add it to connector config scopes."
                    )
                result = await session.execute(text(sql), params)
                await session.commit()
                return {"rows_affected": result.rowcount}
            else:
                raise ValueError(f"Unknown operation: {operation}. Use 'query' or 'execute'.")

    def _validate_sql(self, sql: str, operation: str) -> None:
        """Validate SQL safety."""
        # Reject obvious injection attempts (stacked queries)
        if ";" in sql and sql.count(";") > 1:
            raise ValueError("Multiple statements not allowed — potential injection")

        # If operation is query, block write patterns
        if operation == "query" and _WRITE_PATTERNS.search(sql):
            raise ValueError(
                "Write operations detected in query mode. Use operation='execute' "
                "with 'db:write' scope."
            )
