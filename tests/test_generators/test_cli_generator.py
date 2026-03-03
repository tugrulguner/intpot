"""Tests for the CLI generator."""

from __future__ import annotations

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
