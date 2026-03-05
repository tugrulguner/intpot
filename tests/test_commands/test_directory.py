"""Tests for directory discovery mode and --output flag in CLI commands."""

from __future__ import annotations

import textwrap
from pathlib import Path

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()

MCP_SOURCE = """\
from fastmcp import FastMCP
mcp = FastMCP("test")

@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b
"""

CLI_SOURCE = """\
import typer
app = typer.Typer()

@app.command()
def hello(name: str = typer.Argument(..., help="Name")) -> None:
    typer.echo(f"Hello {name}")
"""

API_SOURCE = """\
from fastapi import FastAPI
app = FastAPI()

@app.post("/add")
def add(a: int, b: int) -> dict:
    return {"result": a + b}
"""


def _write(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content))
    return p


def test_directory_to_cli(tmp_path: Path):
    _write(tmp_path, "server.py", MCP_SOURCE)
    _write(tmp_path, "api.py", API_SOURCE)
    result = runner.invoke(app, ["to", "cli", str(tmp_path)])
    assert result.exit_code == 0
    assert "def add(" in result.output


def test_directory_to_cli_with_output(tmp_path: Path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write(src, "server.py", MCP_SOURCE)
    result = runner.invoke(app, ["to", "cli", str(src), "--output", str(out)])
    assert result.exit_code == 0
    generated = list(out.glob("*.py"))
    assert len(generated) == 1
    assert "typer" in generated[0].read_text()


def test_directory_to_mcp(tmp_path: Path):
    _write(tmp_path, "cli.py", CLI_SOURCE)
    result = runner.invoke(app, ["to", "mcp", str(tmp_path)])
    assert result.exit_code == 0
    assert "FastMCP" in result.output


def test_directory_to_api(tmp_path: Path):
    _write(tmp_path, "cli.py", CLI_SOURCE)
    result = runner.invoke(app, ["to", "api", str(tmp_path)])
    assert result.exit_code == 0
    assert "FastAPI" in result.output


def test_directory_no_convertible_sources(tmp_path: Path):
    _write(tmp_path, "cli.py", CLI_SOURCE)
    result = runner.invoke(app, ["to", "cli", str(tmp_path)])
    assert result.exit_code == 1
    assert "No convertible sources found" in result.output


def test_single_file_with_output(tmp_path: Path, tmp_source):
    source = tmp_source(MCP_SOURCE)
    out_file = tmp_path / "output.py"
    result = runner.invoke(app, ["to", "cli", str(source), "--output", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    assert "typer" in out_file.read_text()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "intpot" in result.output


def test_init_path_separator():
    result = runner.invoke(app, ["init", "../../bad", "--type", "mcp"])
    assert result.exit_code == 1
    assert "path separators" in result.output
