"""Tests for the MCP generator."""

from __future__ import annotations

import asyncio

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


def test_generated_mcp_filters_locals_in_async_bodies():
    tool = ToolInfo(
        name="echo",
        description="Echo a value.",
        parameters=[],
        return_type="str",
        function_body=(
            'global status\nawait asyncio.sleep(0)\nstatus = "ok"\nreturn "done"'
        ),
        is_async=True,
        source_imports=["import asyncio", "from fastapi import status"],
    )

    code = MCPGenerator().generate([tool])
    namespace: dict[str, object] = {}
    exec(compile(code, "<generated>", "exec", dont_inherit=True), namespace)

    assert "from fastapi import status" not in code
    assert asyncio.run(namespace["echo"]()) == "done"  # type: ignore[operator]
