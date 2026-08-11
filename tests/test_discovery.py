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


def test_one_unimportable_file_does_not_abort_the_scan(tmp_path: Path, capsys):
    """Detection executes each candidate, so a module can raise anything.

    Only DetectionError, ImportError and OSError were caught, and everything
    else propagated out of the scan — one bad file took down the whole run and
    the good ones were never converted.
    """
    _write(
        tmp_path,
        "boom.py",
        """\
        from fastmcp import FastMCP
        mcp = FastMCP("boom")
        raise ValueError("module-level failure")
        """,
    )
    _write(
        tmp_path,
        "good.py",
        """\
        from fastmcp import FastMCP
        mcp = FastMCP("good")

        @mcp.tool()
        def hello(name: str) -> str:
            return name
        """,
    )

    results = discover_sources(tmp_path)

    assert [p.name for p, _, _ in results] == ["good.py"]
    assert "SKIP (import failed)" in capsys.readouterr().err


def test_an_import_failure_is_reported_without_verbose(tmp_path: Path, capsys):
    """A file that looked like an app and yielded nothing is worth saying out loud."""
    _write(
        tmp_path,
        "boom.py",
        """\
        from fastmcp import FastMCP
        mcp = FastMCP("boom")
        raise RuntimeError("nope")
        """,
    )

    discover_sources(tmp_path, verbose=False)

    err = capsys.readouterr().err
    assert "boom.py" in err
    assert "RuntimeError: nope" in err


def test_files_without_an_app_stay_quiet(tmp_path: Path, capsys):
    """The common case — most files are not apps — must not be noisy."""
    _write(tmp_path, "plain.py", "x = 42\n")

    results = discover_sources(tmp_path)

    assert results == []
    assert capsys.readouterr().err == ""
