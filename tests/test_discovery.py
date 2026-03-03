"""Tests for directory discovery."""

from __future__ import annotations

import textwrap
from pathlib import Path

from intpot.core.discovery import discover_sources
from intpot.core.models import SourceType


def _write(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


def test_discover_finds_apps(tmp_path: Path):
    _write(
        tmp_path,
        "server.py",
        """\
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def hello(name: str) -> str:
            return name
        """,
    )
    _write(
        tmp_path,
        "app.py",
        """\
        import typer
        app = typer.Typer()

        @app.command()
        def hello(name: str = typer.Argument(...)) -> None:
            typer.echo(name)
        """,
    )

    results = discover_sources(tmp_path)
    assert len(results) == 2
    types = {st for _, st, _ in results}
    assert SourceType.MCP in types
    assert SourceType.CLI in types


def test_discover_skips_broken(tmp_path: Path):
    _write(
        tmp_path,
        "good.py",
        """\
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def hello(name: str) -> str:
            return name
    """,
    )
    _write(tmp_path, "bad.py", "def this is broken syntax {{{{")

    results = discover_sources(tmp_path)
    assert len(results) == 1


def test_discover_empty_dir(tmp_path: Path):
    results = discover_sources(tmp_path)
    assert results == []


def test_discover_skips_pycache(tmp_path: Path):
    _write(
        tmp_path,
        "__pycache__/cached.py",
        """\
        from fastmcp import FastMCP
        mcp = FastMCP("test")

        @mcp.tool()
        def hello(name: str) -> str:
            return name
        """,
    )

    results = discover_sources(tmp_path)
    assert results == []
