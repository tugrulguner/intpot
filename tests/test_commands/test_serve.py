"""Tests for the intpot serve command."""

from __future__ import annotations

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_serve_help():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    # Strip ANSI codes for reliable matching
    import re

    clean = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--cli" in clean
    assert "--api" in clean
    assert "--mcp" in clean


def test_serve_no_mode(tmp_source):
    source = tmp_source("""
        from intpot import App
        app = App("test")

        @app.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """)
    result = runner.invoke(app, ["serve", str(source)])
    assert result.exit_code == 1
    assert "exactly one mode" in result.output


def test_serve_file_not_found():
    result = runner.invoke(app, ["serve", "/nonexistent.py", "--cli"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_serve_no_app_found(tmp_source):
    source = tmp_source("""
        x = 42
    """)
    result = runner.invoke(app, ["serve", str(source), "--cli"])
    assert result.exit_code == 1
    assert "No intpot App" in result.output
