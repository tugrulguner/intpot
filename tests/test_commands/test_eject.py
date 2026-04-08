"""Tests for the intpot eject command."""

from __future__ import annotations

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_eject_help():
    result = runner.invoke(app, ["eject", "--help"])
    assert result.exit_code == 0
    assert "--to" in result.output


def test_eject_to_cli(tmp_source):
    source = tmp_source('''
        from intpot import App
        app = App("test")

        @app.tool()
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"
    ''')
    result = runner.invoke(app, ["eject", str(source), "--to", "cli"])
    assert result.exit_code == 0
    assert "import typer" in result.output
    assert "def greet(" in result.output


def test_eject_to_api(tmp_source):
    source = tmp_source('''
        from intpot import App
        app = App("test")

        @app.tool()
        def add(a: int, b: int) -> int:
            """Add numbers."""
            return a + b
    ''')
    result = runner.invoke(app, ["eject", str(source), "--to", "api"])
    assert result.exit_code == 0
    assert "from fastapi import FastAPI" in result.output
    assert "add" in result.output


def test_eject_to_mcp(tmp_source):
    source = tmp_source('''
        from intpot import App
        app = App("test")

        @app.tool()
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello, {name}!"
    ''')
    result = runner.invoke(app, ["eject", str(source), "--to", "mcp"])
    assert result.exit_code == 0
    assert "from fastmcp import FastMCP" in result.output
    assert "def greet(" in result.output


def test_eject_to_file(tmp_source, tmp_path):
    source = tmp_source('''
        from intpot import App
        app = App("test")

        @app.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    ''')
    output = tmp_path / "out" / "cli_app.py"
    result = runner.invoke(
        app, ["eject", str(source), "--to", "cli", "--output", str(output)]
    )
    assert result.exit_code == 0
    assert output.exists()
    content = output.read_text()
    assert "import typer" in content


def test_eject_invalid_target(tmp_source):
    source = tmp_source('''
        from intpot import App
        app = App("test")

        @app.tool()
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    ''')
    result = runner.invoke(app, ["eject", str(source), "--to", "invalid"])
    assert result.exit_code == 1


def test_eject_file_not_found():
    result = runner.invoke(app, ["eject", "/nonexistent.py", "--to", "cli"])
    assert result.exit_code == 1
    assert "not found" in result.output
