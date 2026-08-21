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


# ---------------------------------------------------------------------------
# Output mirrors the source tree
#
# Outputs used to be named from the source basename alone, so `alpha/tools.py`
# and `beta/tools.py` both wrote `tools_mcp.py` — two success lines, one file,
# and whichever converted first was gone (#92).
# ---------------------------------------------------------------------------


def _nested_project(tmp_path: Path) -> Path:
    """A root-level source plus two sharing a basename in sibling packages."""
    project = tmp_path / "project"
    for package, tool in (("alpha", "alpha_only"), ("beta", "beta_only")):
        directory = project / package
        directory.mkdir(parents=True)
        (directory / "tools.py").write_text(
            textwrap.dedent(f"""\
                import typer
                app = typer.Typer()

                @app.command()
                def {tool}(x: int) -> None:
                    "From {package}."
                    typer.echo(x)
                """)
        )
    (project / "root_tool.py").write_text(
        textwrap.dedent("""\
            import typer
            app = typer.Typer()

            @app.command()
            def root_only(x: int) -> None:
                "At the root."
                typer.echo(x)
            """)
    )
    return project


def _tool_names(path: Path) -> list[str]:
    """Import a generated MCP module and ask it which tools it registered."""
    import asyncio
    import importlib.util

    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registered = asyncio.run(module.mcp.local_provider._list_tools())
    return sorted(tool.name for tool in registered)


def test_sources_sharing_a_basename_both_survive(tmp_path: Path):
    project = _nested_project(tmp_path)
    out = tmp_path / "out"

    result = runner.invoke(app, ["to", "mcp", str(project), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*.py")) == [
        "alpha/tools_mcp.py",
        "beta/tools_mcp.py",
        "root_tool_mcp.py",
    ]


def test_each_generated_file_kept_its_own_tool(tmp_path: Path):
    """Three files on disk proves nothing if two of them hold the same tool."""
    project = _nested_project(tmp_path)
    out = tmp_path / "out"

    runner.invoke(app, ["to", "mcp", str(project), "-o", str(out)])

    assert _tool_names(out / "alpha" / "tools_mcp.py") == ["alpha_only"]
    assert _tool_names(out / "beta" / "tools_mcp.py") == ["beta_only"]
    assert _tool_names(out / "root_tool_mcp.py") == ["root_only"]


def test_a_root_level_source_stays_at_the_output_root(tmp_path: Path):
    project = _nested_project(tmp_path)
    out = tmp_path / "out"

    runner.invoke(app, ["to", "mcp", str(project), "-o", str(out)])

    assert (out / "root_tool_mcp.py").exists()
    assert not (out / "project").exists()


def test_dry_run_names_the_paths_a_real_run_would_write(tmp_path: Path):
    """One destination calculation, or dry-run quietly stops being a preview."""
    project = _nested_project(tmp_path)
    out = tmp_path / "out"

    preview = runner.invoke(
        app, ["to", "mcp", str(project), "-o", str(out), "--dry-run"]
    )
    assert preview.exit_code == 0, preview.output
    assert not out.exists(), "--dry-run wrote files"

    previewed = sorted(
        line.removeprefix("# --- Would generate: ").removesuffix(" ---")
        for line in preview.stdout.splitlines()
        if line.startswith("# --- Would generate:")
    )

    runner.invoke(app, ["to", "mcp", str(project), "-o", str(out)])
    written = sorted(str(p) for p in out.rglob("*.py"))

    assert previewed == written


def test_intermediate_output_directories_are_created(tmp_path: Path):
    project = _nested_project(tmp_path)
    out = tmp_path / "does" / "not" / "exist"

    result = runner.invoke(app, ["to", "mcp", str(project), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert (out / "alpha" / "tools_mcp.py").exists()


def test_stdout_mode_identifies_sources_by_relative_path(tmp_path: Path):
    """`# --- tools.py ---` twice tells you nothing about which is which."""
    project = _nested_project(tmp_path)

    result = runner.invoke(app, ["to", "mcp", str(project)])

    headers = [line for line in result.stdout.splitlines() if line.startswith("# --- ")]
    assert "# --- alpha/tools.py ---" in headers
    assert "# --- beta/tools.py ---" in headers


def test_a_colliding_destination_is_refused_before_anything_is_written(
    tmp_path: Path, monkeypatch
):
    """Mirroring makes this unreachable; the guard is what proves it stays so.

    Forcing two sources onto one destination must fail with both named and
    nothing on disk, rather than writing one and reporting two.
    """
    from intpot.commands import _convert

    project = _nested_project(tmp_path)
    out = tmp_path / "out"
    monkeypatch.setattr(
        _convert, "_mirrored_destination", lambda *_args, **_kwargs: out / "same.py"
    )

    result = runner.invoke(app, ["to", "mcp", str(project), "-o", str(out)])

    assert result.exit_code == 1
    assert "both map to" in result.output
    assert not out.exists()
