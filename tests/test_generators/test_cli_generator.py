"""Tests for the CLI generator."""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from intpot.core.generators.cli import CLIGenerator
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def test_generate_cli_app():
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
        ToolInfo(
            name="greet",
            description="Greet someone.",
            parameters=[
                ParameterInfo(name="name", type_annotation="str", default=_SENTINEL),
                ParameterInfo(name="greeting", type_annotation="str", default="Hello"),
            ],
        ),
    ]

    code = CLIGenerator().generate(tools)

    assert "import typer" in code
    assert "app = typer.Typer()" in code
    assert "@app.command()" in code
    assert "def add(" in code
    assert "def greet(" in code
    assert "typer.Argument(..." in code
    assert "typer.Option('Hello'" in code


def test_generate_empty():
    code = CLIGenerator().generate([])
    assert "import typer" in code
    assert "app = typer.Typer()" in code


def _run_generated(code: str, args: list[str]) -> Any:
    """Execute generated CLI code and invoke it, returning the Typer result."""
    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)
    return CliRunner().invoke(namespace["app"], args)


def test_generated_cli_prints_the_return_value():
    """Typer discards return values, so a preserved body needs an explicit echo."""
    tools = [
        ToolInfo(
            name="add",
            description="Add two numbers.",
            parameters=[
                ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
                ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
            ],
            return_type="int",
            function_body="return a + b",
        ),
    ]

    result = _run_generated(CLIGenerator().generate(tools), ["2", "3"])

    assert result.exit_code == 0
    assert result.output.strip() == "5"


def test_generated_cli_runs_an_async_body():
    """`async def` under @app.command() is never awaited, so the body is driven
    through asyncio.run from a synchronous command instead."""
    tools = [
        ToolInfo(
            name="fetch",
            description="Fetch a URL.",
            parameters=[
                ParameterInfo(name="url", type_annotation="str", default=_SENTINEL),
            ],
            return_type="str",
            is_async=True,
            function_body='return f"fetched {url}"',
        ),
    ]

    result = _run_generated(CLIGenerator().generate(tools), ["example.com"])

    assert result.exit_code == 0
    assert "fetched example.com" in result.output


def test_generated_cli_stays_quiet_when_the_body_returns_nothing():
    """A body that echoes itself must not also print a bare `None`."""
    tools = [
        ToolInfo(
            name="log",
            description="Log a message.",
            parameters=[
                ParameterInfo(name="msg", type_annotation="str", default=_SENTINEL),
            ],
            return_type="None",
            function_body="typer.echo(msg)",
        ),
    ]

    result = _run_generated(CLIGenerator().generate(tools), ["hello"])

    assert result.exit_code == 0
    assert result.output.strip() == "hello"
