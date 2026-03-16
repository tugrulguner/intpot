"""Extended tests for Python API features."""

from __future__ import annotations

import pytest

import intpot
from intpot.core.detector import DetectionError
from intpot.core.models import SourceType


def test_repr_with_source_path(tmp_source):
    source = tmp_source("""
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """)
    app = intpot.load(str(source))
    r = repr(app)
    assert "IntpotApp" in r
    assert "mcp" in r
    assert "source_path=" in r


def test_repr_without_source_path():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    r = repr(app)
    assert "IntpotApp" in r
    assert "source_path" not in r


def test_tools_property():
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    tools = app.tools
    assert len(tools) == 1
    assert tools[0].name == "greet"


def test_write_with_source_type_enum(tmp_path):
    from fastmcp import FastMCP

    mcp = FastMCP("test")

    @mcp.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    app = intpot.load(mcp)
    out = tmp_path / "cli_app.py"
    app.write(out, SourceType.CLI)
    assert out.exists()
    assert "typer" in out.read_text()


def test_detect_instance_directly():
    import typer

    from intpot.core.detector import detect_instance

    cli = typer.Typer()
    source_type, obj = detect_instance(cli)
    assert source_type == SourceType.CLI
    assert obj is cli


def test_detect_instance_unknown():
    from intpot.core.detector import detect_instance

    with pytest.raises(DetectionError, match="Unrecognized"):
        detect_instance("not an app")


def test_pascal_case_in_api_output():
    import typer

    cli = typer.Typer()

    @cli.command()
    def add_numbers(
        a: int = typer.Argument(..., help="First"),
        b: int = typer.Argument(..., help="Second"),
    ) -> None:
        typer.echo(a + b)

    code = intpot.load(cli).to_api()
    assert "def add_numbers(" in code
    assert "a: int" in code
    assert "b: int" in code


def test_http_method_preserved():
    from fastapi import FastAPI

    api = FastAPI()

    @api.get("/items")
    def items() -> dict:
        return {"items": []}

    app = intpot.load(api)
    tools = app.tools
    assert tools[0].http_method == "GET"
