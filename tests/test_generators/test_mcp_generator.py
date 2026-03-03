"""Tests for the MCP generator."""

from __future__ import annotations

from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def test_generate_mcp_server():
    tools = [
        ToolInfo(
            name="add",
            description="Add two numbers.",
            parameters=[
                ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
                ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
            ],
            return_type="int",
        ),
    ]

    code = MCPGenerator().generate(tools)

    assert "from fastmcp import FastMCP" in code
    assert "@mcp.tool()" in code
    assert "def add(" in code
    assert "a: int," in code
