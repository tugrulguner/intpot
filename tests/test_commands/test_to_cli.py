"""Tests for the to cli command."""

from __future__ import annotations

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_mcp_to_cli(tmp_source):
    source = tmp_source('''
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
    ''')
    result = runner.invoke(app, ["to", "cli", str(source)])
    assert result.exit_code == 0
    assert "def add(" in result.output
    assert "typer" in result.output


def test_api_to_cli(tmp_source):
    source = tmp_source('''
        from fastapi import FastAPI
        app = FastAPI()

        @app.post("/add")
        def add(a: int, b: int) -> dict:
            """Add numbers."""
            return {"result": a + b}
    ''')
    result = runner.invoke(app, ["to", "cli", str(source)])
    assert result.exit_code == 0
    assert "def add(" in result.output


def test_cli_to_cli_fails(tmp_source):
    source = tmp_source("""
        import typer
        app = typer.Typer()

        @app.command()
        def hello() -> None:
            pass
    """)
    result = runner.invoke(app, ["to", "cli", str(source)])
    assert result.exit_code == 1
