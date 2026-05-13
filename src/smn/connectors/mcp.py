"""MCP (Model Context Protocol) connector — discover and invoke MCP tools.

Wraps MCP server tools as first-class SMN tools with full governance:
- Tool discovery from MCP server manifests
- Automatic ToolSpec generation with scope mapping
- JSON-RPC invocation over stdio or HTTP transports
- Connection lifecycle management

Usage:
    adapter = MCPToolAdapter(
        server=MCPServerConfig(name="fs", command="npx @mcp/filesystem")
    )
    await adapter.connect()
    tools = adapter.get_tools()
    # tools are standard SMN tool callables with _tool_spec attached
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from smn.core.tools import ToolSpec

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""

    name: str
    command: str | None = None  # stdio transport: command to run
    url: str | None = None  # HTTP/SSE transport: server URL
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)  # SMN scopes for all tools from this server
    requires_approval: bool = False  # default approval requirement


@dataclass
class MCPTool:
    """An MCP tool definition from a server manifest."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


class MCPToolAdapter:
    """Adapts MCP server tools into SMN-governed tools.

    Handles connection lifecycle, tool discovery, and invocation.
    Each MCP tool becomes a standard SMN ToolSpec that flows through
    the same governance gates as native tools.
    """

    def __init__(self, server: MCPServerConfig) -> None:
        self._server = server
        self._process: asyncio.subprocess.Process | None = None
        self._tools: list[MCPTool] = []
        self._request_id = 0
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def server_name(self) -> str:
        return self._server.name

    async def connect(self) -> None:
        """Start the MCP server process (stdio transport)."""
        if self._server.command is None:
            raise ValueError("MCP server requires a command (stdio) or url (HTTP)")

        cmd_parts = [self._server.command] + self._server.args
        self._process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**dict(__import__("os").environ), **self._server.env} if self._server.env else None,
        )
        self._connected = True

        # Initialize: send initialize request
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smn", "version": "0.1.0"},
        })

        # Discover tools
        result = await self._send_request("tools/list", {})
        if result and "tools" in result:
            for t in result["tools"]:
                self._tools.append(MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_name=self._server.name,
                ))
        logger.info(
            "MCP server %s: discovered %d tools", self._server.name, len(self._tools)
        )

    async def disconnect(self) -> None:
        """Terminate the MCP server process."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
        self._connected = False

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC request and read the response."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("MCP server not connected")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        payload = json.dumps(request) + "\n"
        self._process.stdin.write(payload.encode())
        await self._process.stdin.drain()

        line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30.0)
        if not line:
            return None

        response = json.loads(line.decode())
        if "error" in response:
            logger.error("MCP error: %s", response["error"])
            raise RuntimeError(f"MCP error: {response['error'].get('message', 'unknown')}")
        return response.get("result")

    async def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Invoke an MCP tool and return the result."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        if result and "content" in result:
            # Extract text content from MCP response
            parts = []
            for item in result["content"]:
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
            return {"result": "\n".join(parts)} if parts else result
        return result or {}

    def get_tools(self) -> list[Callable]:
        """Convert discovered MCP tools into SMN tool callables.

        Each returned callable has a ``_tool_spec`` attribute
        matching the SMN ToolSpec protocol, so it works with
        ``Agent(tools=[...])`` seamlessly.
        """
        callables: list[Callable] = []
        for mcp_tool in self._tools:
            callables.append(self._make_tool_callable(mcp_tool))
        return callables

    def _make_tool_callable(self, mcp_tool: MCPTool) -> Callable:
        """Create an async callable with ToolSpec from an MCP tool definition."""
        adapter = self

        # Convert MCP input schema to SMN parameter format
        properties = mcp_tool.input_schema.get("properties", {})
        required = set(mcp_tool.input_schema.get("required", []))
        params: dict[str, dict[str, Any]] = {}
        for pname, pinfo in properties.items():
            params[pname] = {
                "type": pinfo.get("type", "string"),
                "required": pname in required,
            }

        spec = ToolSpec(
            name=f"mcp_{mcp_tool.server_name}_{mcp_tool.name}",
            description=f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}",
            func=None,  # placeholder — replaced below
            parameters=params,
            scopes=tuple(self._server.scopes),
            requires_approval=self._server.requires_approval,
        )

        async def _invoke(**kwargs: Any) -> Any:
            return await adapter.invoke_tool(mcp_tool.name, kwargs)

        # Attach spec to the callable
        _invoke._tool_spec = ToolSpec(  # type: ignore[attr-defined]
            name=spec.name,
            description=spec.description,
            func=_invoke,
            parameters=spec.parameters,
            scopes=spec.scopes,
            requires_approval=spec.requires_approval,
        )
        return _invoke
