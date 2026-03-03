"""Tests for the MCP inspector."""

from __future__ import annotations

from fastmcp import FastMCP

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
