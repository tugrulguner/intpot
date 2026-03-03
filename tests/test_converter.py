"""Tests for the Python API (intpot.load / IntpotApp)."""

from __future__ import annotations

import pytest

import intpot
from intpot.converter import IntpotApp
from intpot.core.detector import DetectionError
from intpot.core.models import SourceType


def test_load_from_file(tmp_source):
    source = tmp_source("""
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """)
    app = intpot.load(str(source))
    assert isinstance(app, IntpotApp)
    assert app.source_type == SourceType.MCP
    assert app.source_path is not None


def test_load_from_mcp_instance():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    assert app.source_type == SourceType.MCP
    assert app.app is mcp
    assert app.source_path is None


def test_load_from_typer_instance():
    import typer

    cli = typer.Typer()

    @cli.command()
    def hello(name: str = typer.Argument(..., help="Name")) -> None:
        typer.echo(f"Hello {name}")

    app = intpot.load(cli)
    assert app.source_type == SourceType.CLI
    assert app.app is cli


def test_load_from_fastapi_instance():
    from fastapi import FastAPI

    api = FastAPI()

    @api.post("/greet")
    def greet(name: str) -> dict:
        return {"message": f"Hello, {name}!"}

    app = intpot.load(api)
    assert app.source_type == SourceType.API
    assert app.app is api


def test_to_cli_from_mcp():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    code = intpot.load(mcp).to_cli()
    assert "import typer" in code
    assert "def greet(" in code


def test_to_mcp_from_cli():
    import typer

    cli = typer.Typer()

    @cli.command()
    def hello(name: str = typer.Argument(..., help="Name")) -> None:
        typer.echo(f"Hello {name}")

    code = intpot.load(cli).to_mcp()
    assert "from fastmcp import FastMCP" in code
    assert "def hello(" in code


def test_to_api_from_cli():
    import typer

    cli = typer.Typer()

    @cli.command()
    def hello(name: str = typer.Argument(..., help="Name")) -> None:
        typer.echo(f"Hello {name}")

    code = intpot.load(cli).to_api()
    assert "from fastapi import FastAPI" in code
    assert "hello" in code


def test_same_type_raises():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    with pytest.raises(ValueError, match=r"already.*MCP"):
        app.to_mcp()


def test_unknown_instance():
    with pytest.raises(DetectionError, match="Unrecognized"):
        intpot.load(42)
