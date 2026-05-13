"""Tests for MCP tool adapter — tool discovery and invocation wrapping."""

from __future__ import annotations

import asyncio

import pytest

from smn.connectors.mcp import MCPServerConfig, MCPTool, MCPToolAdapter
from smn.core.tools import ToolSpec


class TestMCPServerConfig:
    def test_defaults(self):
        cfg = MCPServerConfig(name="test")
        assert cfg.name == "test"
        assert cfg.command is None
        assert cfg.scopes == []

    def test_with_command(self):
        cfg = MCPServerConfig(name="fs", command="npx @mcp/filesystem", args=["--root", "/tmp"])
        assert cfg.command == "npx @mcp/filesystem"
        assert cfg.args == ["--root", "/tmp"]


class TestMCPTool:
    def test_creation(self):
        tool = MCPTool(
            name="read_file",
            description="Read a file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            server_name="fs",
        )
        assert tool.name == "read_file"
        assert tool.server_name == "fs"


class TestMCPToolAdapter:
    def test_initial_state(self):
        cfg = MCPServerConfig(name="test", command="echo")
        adapter = MCPToolAdapter(cfg)
        assert not adapter.is_connected
        assert adapter.server_name == "test"

    def test_make_tool_callable(self):
        cfg = MCPServerConfig(name="fs", command="echo", scopes=["fs:read"])
        adapter = MCPToolAdapter(cfg)

        mcp_tool = MCPTool(
            name="read_file",
            description="Read a file from disk",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "encoding": {"type": "string"},
                },
                "required": ["path"],
            },
            server_name="fs",
        )

        callable_tool = adapter._make_tool_callable(mcp_tool)
        spec = callable_tool._tool_spec

        assert isinstance(spec, ToolSpec)
        assert spec.name == "mcp_fs_read_file"
        assert "MCP:fs" in spec.description
        assert spec.scopes == ("fs:read",)
        assert "path" in spec.parameters
        assert spec.parameters["path"]["required"] is True
        assert spec.parameters["encoding"]["required"] is False

    def test_get_tools_empty(self):
        cfg = MCPServerConfig(name="test", command="echo")
        adapter = MCPToolAdapter(cfg)
        assert adapter.get_tools() == []

    def test_get_tools_with_discovered(self):
        cfg = MCPServerConfig(name="fs", command="echo", scopes=["fs:*"])
        adapter = MCPToolAdapter(cfg)
        # Simulate discovered tools
        adapter._tools = [
            MCPTool(
                name="read",
                description="Read",
                input_schema={"type": "object", "properties": {"p": {"type": "string"}}},
                server_name="fs",
            ),
            MCPTool(
                name="write",
                description="Write",
                input_schema={"type": "object", "properties": {"p": {"type": "string"}}},
                server_name="fs",
            ),
        ]
        tools = adapter.get_tools()
        assert len(tools) == 2
        assert all(hasattr(t, "_tool_spec") for t in tools)
        names = {t._tool_spec.name for t in tools}
        assert names == {"mcp_fs_read", "mcp_fs_write"}

    @pytest.mark.asyncio
    async def test_connect_requires_command_or_url(self):
        cfg = MCPServerConfig(name="test")
        adapter = MCPToolAdapter(cfg)
        with pytest.raises(ValueError, match="requires a command"):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_invoke_tool_not_connected(self):
        cfg = MCPServerConfig(name="test", command="echo")
        adapter = MCPToolAdapter(cfg)
        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.invoke_tool("test", {})
