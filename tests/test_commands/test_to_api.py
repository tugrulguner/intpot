"""Tests for the to api command."""

from __future__ import annotations

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_mcp_to_api(tmp_source):
    source = tmp_source('''
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
    ''')
    result = runner.invoke(app, ["to", "api", str(source)])
    assert result.exit_code == 0
    assert "def add(" in result.output
    assert "fastapi" in result.output.lower()


def test_cli_to_api(tmp_source):
    source = tmp_source('''
        import typer
        app = typer.Typer()

        @app.command()
        def add(
            a: int = typer.Argument(..., help="First"),
            b: int = typer.Argument(..., help="Second"),
        ) -> None:
            """Add two numbers."""
            pass
    ''')
    result = runner.invoke(app, ["to", "api", str(source)])
    assert result.exit_code == 0
    assert "def add(" in result.output


def test_cli_to_api_return_wrapped_in_dict(tmp_source):
    source = tmp_source('''
        import typer
        app = typer.Typer()

        @app.command()
        def greet(
            name: str = typer.Argument(..., help="Name to greet"),
            greeting: str = typer.Option("Hello", help="Greeting to use"),
        ) -> None:
            typer.echo(f"{greeting}, {name}!")
    ''')
    result = runner.invoke(app, ["to", "api", str(source)])
    assert result.exit_code == 0
    # ast.unparse uses single quotes; check for dict key "result"
    assert "'result'" in result.output


def test_api_to_api_fails(tmp_source):
    source = tmp_source("""
        from fastapi import FastAPI
        app = FastAPI()
    """)
    result = runner.invoke(app, ["to", "api", str(source)])
    assert result.exit_code == 1
