"""Tests for the CLI inspector."""

from __future__ import annotations

import typer

from intpot.core.inspectors.cli import CLIInspector


def test_inspect_typer_commands():
    app = typer.Typer()

    @app.command()
    def add(
        a: int = typer.Argument(..., help="First number"),
        b: int = typer.Argument(..., help="Second number"),
    ) -> None:
        """Add two numbers."""
        pass

    @app.command()
    def greet(
        name: str = typer.Argument(..., help="Name"),
        greeting: str = typer.Option("Hello", help="Greeting"),
    ) -> None:
        """Greet someone."""
        pass

    inspector = CLIInspector()
    tools = inspector.inspect(app)

    assert len(tools) == 2

    add_tool = next(t for t in tools if t.name == "add")
    assert add_tool.description == "Add two numbers."
    assert len(add_tool.parameters) == 2
    assert add_tool.parameters[0].name == "a"
    assert add_tool.parameters[0].type_annotation == "int"
    assert add_tool.parameters[0].required
    assert add_tool.parameters[0].description == "First number"

    greet_tool = next(t for t in tools if t.name == "greet")
    assert greet_tool.parameters[1].name == "greeting"
    assert greet_tool.parameters[1].default == "Hello"
    assert not greet_tool.parameters[1].required


def test_inspect_empty_typer():
    app = typer.Typer()
    inspector = CLIInspector()
    tools = inspector.inspect(app)
    assert tools == []
