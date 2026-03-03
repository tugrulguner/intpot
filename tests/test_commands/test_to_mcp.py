"""Tests for the to mcp command."""

from __future__ import annotations

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_cli_to_mcp(tmp_source):
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
    result = runner.invoke(app, ["to", "mcp", str(source)])
    assert result.exit_code == 0
    assert "def add(" in result.output
    assert "fastmcp" in result.output.lower()


def test_api_to_mcp(tmp_source):
    source = tmp_source('''
        from fastapi import FastAPI
        app = FastAPI()

        @app.post("/add")
        def add(a: int, b: int) -> dict:
            """Add numbers."""
            return {"result": a + b}
    ''')
    result = runner.invoke(app, ["to", "mcp", str(source)])
    assert result.exit_code == 0
    assert "def add(" in result.output


def test_mcp_to_mcp_fails(tmp_source):
    source = tmp_source("""
        from fastmcp import FastMCP
        mcp = FastMCP("test")
    """)
    result = runner.invoke(app, ["to", "mcp", str(source)])
    assert result.exit_code == 1
