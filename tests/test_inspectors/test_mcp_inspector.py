"""Tests for the MCP inspector."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastmcp import FastMCP

from intpot.core.inspectors.base import InspectionError
from intpot.core.inspectors.mcp import MCPInspector


def test_inspect_mcp_tools():
    mcp = FastMCP("test")

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @mcp.tool()
    def greet(name: str, greeting: str = "Hello") -> str:
        """Greet someone."""
        return f"{greeting}, {name}!"

    inspector = MCPInspector()
    tools = inspector.inspect(mcp)

    assert len(tools) == 2

    add_tool = next(t for t in tools if t.name == "add")
    assert add_tool.description == "Add two numbers."
    assert len(add_tool.parameters) == 2
    assert add_tool.parameters[0].name == "a"
    assert add_tool.parameters[0].type_annotation == "int"
    assert add_tool.parameters[0].required
    assert add_tool.return_type == "int"

    greet_tool = next(t for t in tools if t.name == "greet")
    assert greet_tool.parameters[1].name == "greeting"
    assert greet_tool.parameters[1].default == "Hello"
    assert not greet_tool.parameters[1].required


def test_inspect_empty_mcp():
    mcp = FastMCP("empty")
    inspector = MCPInspector()
    tools = inspector.inspect(mcp)
    assert tools == []


def test_inspect_fastmcp_2_tool_manager_registry():
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    tool = SimpleNamespace(
        fn=greet,
        name="greet",
        description="Greet someone.",
        parameters={"properties": {"name": {"type": "string"}}},
    )
    app = SimpleNamespace(
        _tool_manager=SimpleNamespace(list_tools=lambda: [tool]),
    )

    tools = MCPInspector().inspect(app)

    assert [tool.name for tool in tools] == ["greet"]


def test_inspect_late_fastmcp_2_async_tool_manager_registry():
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    tool = SimpleNamespace(
        fn=greet,
        name="greet",
        description="Greet someone.",
        parameters={"properties": {"name": {"type": "string"}}},
    )

    class ToolManager:
        async def get_tools(self):
            return {"greet": tool}

    tools = MCPInspector().inspect(SimpleNamespace(_tool_manager=ToolManager()))

    assert [inspected.name for inspected in tools] == ["greet"]


def test_inspect_fastmcp_3_local_provider_registry():
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    tool = SimpleNamespace(
        fn=greet,
        name="greet",
        description="Greet someone.",
        parameters={"properties": {"name": {"type": "string"}}},
    )

    class LocalProvider:
        async def _list_tools(self):
            return [tool]

    app = SimpleNamespace(local_provider=LocalProvider())

    tools = MCPInspector().inspect(app)

    assert [tool.name for tool in tools] == ["greet"]


def test_inspect_fastmcp_3_from_a_running_event_loop():
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    tool = SimpleNamespace(
        fn=greet,
        name="greet",
        description="Greet someone.",
        parameters={"properties": {"name": {"type": "string"}}},
    )

    class LocalProvider:
        async def _list_tools(self):
            return [tool]

    async def inspect_inside_loop():
        return MCPInspector().inspect(SimpleNamespace(local_provider=LocalProvider()))

    tools = asyncio.run(inspect_inside_loop())

    assert [inspected.name for inspected in tools] == ["greet"]


def test_inspect_uses_mcp_parameter_schema_descriptions():
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    tool = SimpleNamespace(
        fn=greet,
        name="greet",
        description="Greet someone.",
        parameters={
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Person to greet.",
                }
            }
        },
    )
    app = SimpleNamespace(
        _tool_manager=SimpleNamespace(list_tools=lambda: [tool]),
    )

    [inspected] = MCPInspector().inspect(app)

    assert inspected.parameters[0].description == "Person to greet."


def test_inspect_rejects_unknown_fastmcp_registry_shape():
    with pytest.raises(InspectionError, match="Unsupported FastMCP registry shape"):
        MCPInspector().inspect(SimpleNamespace())


def test_inspect_rejects_unknown_fastmcp_local_provider_shape():
    app = SimpleNamespace(local_provider=SimpleNamespace())

    with pytest.raises(InspectionError, match="Unsupported FastMCP registry shape"):
        MCPInspector().inspect(app)
