"""Tests for the to cli command."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


@pytest.mark.parametrize("target", ["cli", "mcp", "api"])
def test_single_file_detection_failure_is_reported(target, tmp_source):
    source = tmp_source("value = 42")

    result = runner.invoke(app, ["to", target, str(source)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "No FastMCP, Typer, or FastAPI app instance found" in result.stderr
    assert str(source) in result.stderr


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


@pytest.mark.parametrize("target", ["cli", "mcp"])
def test_api_dependency_conversion_fails_cleanly(target, tmp_source):
    source = tmp_source("""
        from typing import Annotated

        from fastapi import Depends, FastAPI

        app = FastAPI()

        def current_user() -> str:
            return "Ada"

        @app.get("/greet")
        def greet(user: Annotated[str, Depends(current_user)]) -> dict:
            return {"message": f"Hello, {user}!"}
    """)

    result = runner.invoke(app, ["to", target, str(source)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "/greet" in result.stderr
    assert "current_user" in result.stderr
    assert "Depends/Security" in result.stderr
    assert "issue #20" in result.stderr
    assert "Traceback" not in result.output


def test_single_file_output_creates_parent_directories(tmp_source, tmp_path):
    source = tmp_source("""
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """)
    output = tmp_path / "generated" / "nested" / "cli.py"

    result = runner.invoke(app, ["to", "cli", str(source), "--output", str(output)])

    assert result.exit_code == 0
    assert output.is_file()
    assert "def greet(" in output.read_text()


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
