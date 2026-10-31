from __future__ import annotations

import pytest
from typer.testing import CliRunner

from intpot.cli import app

SOURCE = """import typer
app = typer.Typer()
def validate(value):
    return value
@app.command()
def mapping() -> None:
    typer.echo("useful")
@app.command()
def blocked(value: str = typer.Option("", callback=validate)) -> None:
    typer.echo(value)
"""


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_cli_selects_only_requested_tool(tmp_source, tmp_path, target):
    source = tmp_source(SOURCE)
    destination = tmp_path / "generated" / "selected.py"
    result = CliRunner().invoke(
        app, ["to", target, str(source), "--tool", "mapping", "-o", str(destination)]
    )
    assert result.exit_code == 0, result.output
    namespace = {}
    exec(destination.read_text(), namespace)
    assert "mapping" in namespace
    assert "blocked" not in namespace


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("name", ["typo", "blocked"])
def test_cli_bad_selection_refuses_before_writes(tmp_source, tmp_path, target, name):
    source = tmp_source(SOURCE)
    destination = tmp_path / "untouched" / "selected.py"
    result = CliRunner().invoke(
        app, ["to", target, str(source), "--tool", name, "-o", str(destination)]
    )
    assert result.exit_code != 0
    assert not destination.parent.exists()
    assert "Traceback" not in result.output
    assert "Unknown" in result.output or "callback" in result.output


def test_cli_selection_applies_to_api_to_cli(tmp_source, tmp_path):
    source = tmp_source("""
        from fastapi import FastAPI
        app = FastAPI()
        @app.get("/mapping")
        def mapping() -> str:
            return "useful"
        @app.get("/other")
        def other() -> str:
            return "excluded"
    """)
    destination = tmp_path / "selected_cli.py"
    result = CliRunner().invoke(
        app, ["to", "cli", str(source), "--tool", "mapping", "-o", str(destination)]
    )
    assert result.exit_code == 0, result.output
    namespace = {}
    exec(destination.read_text(), namespace)
    native = CliRunner().invoke(namespace["app"], [])
    assert native.exit_code == 0
    assert native.output.strip() == "useful"
    assert "other" not in namespace


def test_repeated_cli_selection_retains_selected_callback_guard(tmp_source, tmp_path):
    source = tmp_source(SOURCE)
    destination = tmp_path / "untouched" / "selected.py"
    result = CliRunner().invoke(
        app,
        [
            "to",
            "api",
            str(source),
            "--tool",
            "mapping",
            "--tool",
            "blocked",
            "-o",
            str(destination),
        ],
    )
    assert result.exit_code == 1
    assert "callback" in result.output
    assert not destination.parent.exists()


def test_directory_selection_requires_all_names_before_any_write(tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    (source / "a.py").write_text(SOURCE)
    (source / "b.py").write_text(SOURCE.replace("def mapping", "def other"))
    output = tmp_path / "never_created"
    result = CliRunner().invoke(
        app, ["to", "api", str(source), "--tool", "mapping", "-o", str(output)]
    )
    assert result.exit_code == 1
    assert "Unknown" in result.output
    assert not output.exists()
