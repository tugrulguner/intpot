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


def _two_tool_app(tmp_source):
    return tmp_source("""
        from intpot import App
        app = App("demo")

        @app.tool()
        def add(a: int, b: int) -> int:
            \"\"\"Add two numbers.\"\"\"
            return a + b

        @app.tool()
        def greet(name: str, greeting: str = "Hello") -> str:
            \"\"\"Greet someone.\"\"\"
            return f"{greeting}, {name}!"
    """)


def test_serve_cli_runs_the_named_tool(tmp_source):
    """`serve --cli` was unusable: intpot's own parser rejected the tool's
    arguments, and the ones that got through were discarded before Typer saw
    them."""
    source = _two_tool_app(tmp_source)

    result = runner.invoke(app, ["serve", str(source), "--cli", "add", "2", "3"])

    assert result.exit_code == 0
    assert result.output.strip() == "5"


def test_serve_cli_forwards_options_it_does_not_own(tmp_source):
    source = _two_tool_app(tmp_source)

    result = runner.invoke(
        app, ["serve", str(source), "--cli", "greet", "World", "--greeting", "Hi"]
    )

    assert result.exit_code == 0
    assert "Hi, World!" in result.output


def test_serve_cli_accepts_a_double_dash_separator(tmp_source):
    """`--` is the escape hatch for a flag intpot also defines."""
    source = _two_tool_app(tmp_source)

    result = runner.invoke(app, ["serve", str(source), "--cli", "--", "greet", "World"])

    assert result.exit_code == 0
    assert "Hello, World!" in result.output


def test_serve_restores_argv(tmp_source):
    """serve rewrites sys.argv for the served app; it must put it back."""
    import sys

    source = _two_tool_app(tmp_source)
    before = list(sys.argv)

    runner.invoke(app, ["serve", str(source), "--cli", "add", "1", "1"])

    assert sys.argv == before
