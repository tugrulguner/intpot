"""Tests for framework-to-framework body and return-type transformation."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.models import _SENTINEL, ParameterInfo, SourceType, ToolInfo
from intpot.core.transforms import transform_tools


def _add_tool(body: str, return_type: str = "str") -> ToolInfo:
    return ToolInfo(
        name="add",
        description="Add two numbers.",
        parameters=[
            ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
            ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
        ],
        return_type=return_type,
        function_body=body,
    )


def _to_api(tool: ToolInfo, source: SourceType) -> ToolInfo:
    return transform_tools([tool], source, SourceType.API)[0]


def test_cli_to_api_wraps_a_scalar_return():
    """`-> dict` is only honest if the body actually returns a mapping.

    typer.echo(a + b) becomes `return a + b`, which FastAPI then rejected
    against the dict annotation with a ResponseValidationError.
    """
    result = _to_api(_add_tool("typer.echo(a + b)"), SourceType.CLI)

    assert result.function_body == "return {'result': a + b}"
    assert result.return_type == "dict"


def test_mcp_to_api_wraps_a_scalar_return():
    result = _to_api(_add_tool("return a + b"), SourceType.MCP)

    assert result.function_body == "return {'result': a + b}"
    assert result.return_type == "dict"


def test_a_dict_return_is_not_nested_again():
    """A source already returning a mapping needs no wrapping."""
    tool = _add_tool("return {'sum': a + b}", return_type="dict")

    result = _to_api(tool, SourceType.MCP)

    assert result.function_body == "return {'sum': a + b}"
    assert result.return_type == "dict"


def test_a_body_that_never_returns_is_annotated_none():
    """Falling off the end yields None, which `-> dict` would also reject."""
    tool = ToolInfo(name="ping", description="Ping.", function_body="print('pong')")

    result = _to_api(tool, SourceType.CLI)

    assert result.return_type == "None"


@pytest.mark.parametrize(
    ("body", "return_type"),
    [
        ("if a:\n    return 1", "dict | None"),
        ("if a:\n    return 1\nelse:\n    return 2", "dict"),
        ("try:\n    return 1\nexcept ValueError:\n    pass", "dict | None"),
        ("try:\n    return 1\nexcept ValueError:\n    return 2", "dict"),
        ("for item in []:\n    return item", "dict | None"),
        ("for item in []:\n    pass\nelse:\n    return 1", "dict"),
        ("while True:\n    return 1", "dict"),
        (
            "with suppress(ValueError):\n    raise ValueError\nreturn 1",
            "dict",
        ),
        (
            "match a:\n    case True:\n        return 1\n    case _:\n        return 2",
            "dict",
        ),
        ("match a:\n    case True:\n        return 1", "dict | None"),
        ("return", "None"),
    ],
)
def test_api_annotation_describes_reachable_return_shapes(body, return_type):
    result = _to_api(_add_tool(body), SourceType.MCP)

    assert result.return_type == return_type


def test_returns_inside_a_nested_function_are_left_alone():
    body = "def helper():\n    return a + b\nreturn helper()"

    result = _to_api(_add_tool(body), SourceType.MCP)

    body = result.function_body or ""
    assert "return a + b" in body
    assert "return {'result': helper()}" in body


def test_converted_api_app_serves_a_real_request():
    """The end-to-end check: convert, execute the output, call it."""
    tool = _to_api(_add_tool("typer.echo(a + b)"), SourceType.CLI)
    namespace: dict[str, Any] = {}
    exec(compile(APIGenerator().generate([tool]), "<generated>", "exec"), namespace)

    response = TestClient(namespace["app"]).post("/add", json={"a": 2, "b": 3})

    assert response.status_code == 200
    assert response.json() == {"result": 5}


def test_api_target_does_not_change_other_targets():
    """Wrapping is FastAPI-specific; CLI and MCP output is untouched."""
    cli = transform_tools([_add_tool("return a + b")], SourceType.MCP, SourceType.CLI)[
        0
    ]
    mcp = transform_tools(
        [_add_tool("return a + b", return_type="int")],
        SourceType.API,
        SourceType.MCP,
    )[0]

    assert cli.function_body == "return a + b"
    assert cli.return_type == "str"
    assert mcp.function_body == "return a + b"
    assert mcp.return_type == "int"


def _run_as_cli(tool: ToolInfo, source: SourceType, *args: str):
    """Convert, execute the generated module, and invoke its real Typer command."""
    transformed = transform_tools([tool], source, SourceType.CLI)
    namespace: dict[str, Any] = {}
    code = CLIGenerator().generate(transformed)
    exec(compile(code, "<generated>", "exec"), namespace)
    return CliRunner().invoke(namespace["app"], list(args))


@pytest.mark.parametrize("source", [SourceType.MCP, SourceType.API])
def test_to_cli_preserves_early_return_control_flow(source: SourceType) -> None:
    tool = _add_tool(
        "if a > 0:\n    return a + b\nraise RuntimeError('unreachable side effect')",
        return_type="int",
    )

    result = _run_as_cli(tool, source, "2", "3")

    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "5"


def test_to_cli_preserves_return_inside_loop() -> None:
    tool = _add_tool(
        "for value in (a, b):\n"
        "    return value\n"
        "raise RuntimeError('unreachable side effect')",
        return_type="int",
    )

    result = _run_as_cli(tool, SourceType.MCP, "2", "3")

    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "2"


def test_to_cli_preserves_bare_return() -> None:
    tool = _add_tool(
        "if a > 0:\n    return\nraise RuntimeError('unreachable side effect')",
        return_type="None",
    )

    result = _run_as_cli(tool, SourceType.API, "2", "3")

    assert result.exit_code == 0, result.exception
    assert result.output == ""


def test_to_cli_preserves_async_early_return() -> None:
    tool = _add_tool(
        "if a > 0:\n    return a + b\nraise RuntimeError('unreachable side effect')",
        return_type="int",
    )
    tool.is_async = True

    result = _run_as_cli(tool, SourceType.MCP, "2", "3")

    assert result.exit_code == 0, result.exception
    assert result.output.strip() == "5"


# ---------------------------------------------------------------------------
# typer.echo → return must preserve control flow
#
# Each echo used to become its own `return`, independently of where it sat.
# One inside a loop returned on the first iteration, so a command that printed
# every item produced exactly one — no error, just a quietly wrong answer.
# ---------------------------------------------------------------------------


def _listing_tool(body: str) -> ToolInfo:
    return ToolInfo(
        name="listing",
        description="List things.",
        parameters=[ParameterInfo(name="items", type_annotation="list")],
        return_type="None",
        function_body=body,
    )


def _run_as_mcp(tool: ToolInfo, *args: Any) -> Any:
    """Convert to MCP, execute the generated module, call the tool."""
    import asyncio

    from intpot.core.generators.mcp import MCPGenerator

    tools = transform_tools([tool], SourceType.CLI, SourceType.MCP)
    namespace: dict[str, Any] = {}
    exec(compile(MCPGenerator().generate(tools), "<generated>", "exec"), namespace)
    registered = asyncio.run(namespace["mcp"].local_provider._list_tools())
    return {t.name: t.fn for t in registered}["listing"](*args)


def test_an_echo_in_a_loop_returns_every_line_not_the_first() -> None:
    tool = _listing_tool("for item in items:\n    typer.echo(item)")

    assert _run_as_mcp(tool, ["a", "b", "c"]) == "a\nb\nc"


def test_work_after_an_echo_still_happens() -> None:
    tool = _listing_tool("typer.echo('start')\ntotal = len(items)\ntyper.echo(total)")

    assert _run_as_mcp(tool, ["a", "b"]) == "start\n2"


def test_both_branches_of_a_conditional_are_captured() -> None:
    tool = _listing_tool(
        "if items:\n    typer.echo('some')\nelse:\n    typer.echo('none')"
    )

    assert _run_as_mcp(tool, []) == "none"
    assert _run_as_mcp(tool, ["x"]) == "some"


def test_a_bare_return_still_exits_early_and_returns_what_was_printed() -> None:
    tool = _listing_tool(
        "if not items:\n"
        "    typer.echo('empty')\n"
        "    return\n"
        "for item in items:\n"
        "    typer.echo(item)"
    )

    assert _run_as_mcp(tool, []) == "empty"
    assert _run_as_mcp(tool, ["a", "b"]) == "a\nb"


def test_a_single_trailing_echo_still_returns_its_value_directly() -> None:
    """The common case keeps its clean shape — and its type.

    Accumulating unconditionally would turn `add` into a function returning
    "5" instead of 5.
    """
    tool = transform_tools(
        [_add_tool("typer.echo(a + b)")], SourceType.CLI, SourceType.MCP
    )[0]

    assert tool.function_body == "return a + b"


def test_returns_inside_a_nested_function_are_still_left_alone() -> None:
    tool = _listing_tool(
        "def helper():\n    return 1\ntyper.echo(helper())\ntyper.echo('done')"
    )
    transformed = transform_tools([tool], SourceType.CLI, SourceType.MCP)[0]

    assert "def helper():\n    return 1" in (transformed.function_body or "")
    assert _run_as_mcp(tool, []) == "1\ndone"


def test_a_multi_echo_body_converted_to_api_serves_a_real_request() -> None:
    tool = _listing_tool("for item in items:\n    typer.echo(item)")
    tools = transform_tools([tool], SourceType.CLI, SourceType.API)
    namespace: dict[str, Any] = {}
    exec(compile(APIGenerator().generate(tools), "<generated>", "exec"), namespace)

    response = TestClient(namespace["app"]).post("/listing", json=["a", "b"])

    assert response.status_code == 200, response.text
    assert response.json() == {"result": "a\nb"}


def test_an_echo_inside_a_helper_does_not_survive_into_the_output() -> None:
    """A leftover `typer.echo` is a NameError: nothing imports typer there.

    Skipping nested scopes entirely to protect their `return` statements also
    skipped their echoes. Appending from a nested scope needs no `nonlocal` —
    the list is only mutated, never rebound.
    """
    tool = _listing_tool(
        "def show(x):\n"
        "    typer.echo(x)\n"
        "for item in items:\n"
        "    show(item)\n"
        "typer.echo('done')"
    )
    transformed = transform_tools([tool], SourceType.CLI, SourceType.MCP)[0]

    assert "typer.echo" not in (transformed.function_body or "")
    assert _run_as_mcp(tool, ["a", "b"]) == "a\nb\ndone"
