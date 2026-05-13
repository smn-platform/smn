"""Tests for the tool decorator and schema generation."""

import pytest

from smn.core.tools import get_tool_spec, tool, tools_to_openai_schema


@tool(scopes=["math:read"])
async def add(a: int, b: int) -> dict:
    """Add two numbers."""
    return {"result": a + b}


@tool(scopes=["data:write"], requires_approval=True, cost_estimate_usd=0.05)
async def write_data(key: str, value: str) -> dict:
    """Write a key-value pair."""
    return {"key": key, "value": value}


@tool()
async def no_scope_tool(message: str) -> str:
    """A tool with no scopes."""
    return message


class TestToolDecorator:
    def test_spec_is_attached(self):
        spec = get_tool_spec(add)
        assert spec is not None
        assert spec.name == "add"
        assert spec.description == "Add two numbers."
        assert spec.scopes == ("math:read",)

    def test_parameters_extracted(self):
        spec = get_tool_spec(add)
        assert "a" in spec.parameters
        assert "b" in spec.parameters
        assert spec.parameters["a"]["type"] == "integer"
        assert spec.parameters["b"]["type"] == "integer"

    def test_approval_and_cost(self):
        spec = get_tool_spec(write_data)
        assert spec.requires_approval is True
        assert spec.cost_estimate_usd == 0.05

    def test_empty_scopes(self):
        spec = get_tool_spec(no_scope_tool)
        assert spec.scopes == ()

    @pytest.mark.asyncio
    async def test_tool_callable(self):
        result = await add(a=2, b=3)
        assert result == {"result": 5}


class TestSchemaGeneration:
    def test_openai_schema(self):
        schemas = tools_to_openai_schema([add, write_data])
        assert len(schemas) == 2
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "add"
        assert "a" in schemas[0]["function"]["parameters"]["properties"]

    def test_required_params(self):
        schemas = tools_to_openai_schema([add])
        required = schemas[0]["function"]["parameters"]["required"]
        assert "a" in required
        assert "b" in required
