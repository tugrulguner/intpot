"""Tests for the inspect command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_inspect_cli_source(tmp_source):
    source = tmp_source("""
        import typer
        app = typer.Typer()

        @app.command()
        def greet(name: str) -> None:
            \"\"\"Say hello.\"\"\"
            print(f"Hello {name}")
    """)
    result = runner.invoke(app, ["inspect", str(source)])
    assert result.exit_code == 0
    assert "greet" in result.output
    assert "cli" in result.output


def test_inspect_mcp_source(tmp_source):
    source = tmp_source('''
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
    ''')
    result = runner.invoke(app, ["inspect", str(source)])
    assert result.exit_code == 0
    assert "add" in result.output
    assert "mcp" in result.output


def test_inspect_api_source(tmp_source):
    source = tmp_source('''
        from fastapi import FastAPI
        app = FastAPI()

        @app.post("/add")
        def add(a: int, b: int) -> dict:
            """Add numbers."""
            return {"result": a + b}
    ''')
    result = runner.invoke(app, ["inspect", str(source)])
    assert result.exit_code == 0
    assert "add" in result.output
    assert "api" in result.output


def test_inspect_json_output(tmp_source):
    source = tmp_source('''
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b
    ''')
    result = runner.invoke(app, ["inspect", str(source), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["type"] == "mcp"
    assert len(data[0]["tools"]) == 1
    assert data[0]["tools"][0]["name"] == "add"
    assert len(data[0]["tools"][0]["parameters"]) == 2


def test_inspect_json_has_params(tmp_source):
    source = tmp_source("""
        import typer
        app = typer.Typer()

        @app.command()
        def hello(name: str, count: int = 1) -> None:
            pass
    """)
    result = runner.invoke(app, ["inspect", str(source), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    params = data[0]["tools"][0]["parameters"]
    names = [p["name"] for p in params]
    assert "name" in names
    assert "count" in names


def test_inspect_nonexistent_file():
    result = runner.invoke(app, ["inspect", "/tmp/no_such_file_xyz.py"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
