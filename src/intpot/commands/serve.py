"""Serve an intpot App as CLI, API, or MCP."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from intpot.core.detector import _import_module_from_path


def _find_intpot_app(source_path: Path) -> object:
    """Import a module and find the intpot App instance."""
    from intpot.runtime import App

    module = _import_module_from_path(source_path)
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        obj = getattr(module, attr_name)
        if isinstance(obj, App):
            return obj

    typer.echo(f"Error: No intpot App instance found in {source_path}", err=True)
    raise typer.Exit(1)


def serve_command(
    ctx: typer.Context,
    source: Path = typer.Argument(
        ..., help="Path to a Python file containing an intpot App"
    ),
    cli: bool = typer.Option(False, "--cli", help="Serve as Typer CLI"),
    api: bool = typer.Option(False, "--api", help="Serve as FastAPI"),
    mcp: bool = typer.Option(False, "--mcp", help="Serve as FastMCP server"),
    host: str = typer.Option("0.0.0.0", "--host", help="API server host"),
    port: int = typer.Option(8000, "--port", help="API server port"),
) -> None:
    """Serve an intpot App as CLI, API, or MCP server."""
    from intpot.runtime import App

    selected = [m for m, flag in [("cli", cli), ("api", api), ("mcp", mcp)] if flag]
    if len(selected) != 1:
        typer.echo("Error: Specify exactly one mode: --cli, --api, or --mcp", err=True)
        raise typer.Exit(1)

    source_path = Path(source).resolve()
    if not source_path.exists():
        typer.echo(f"Error: File not found: {source_path}", err=True)
        raise typer.Exit(1)

    app_instance = _find_intpot_app(source_path)
    assert isinstance(app_instance, App)

    mode = selected[0]
    if mode != "cli":
        app_instance.serve(mode=mode, host=host, port=port)
        return

    # The served Typer app reads sys.argv, so hand it the user's arguments in
    # place of our own. Anything intpot did not consume arrives in ctx.args;
    # use `--` to pass through a flag that intpot also defines.
    original_argv = sys.argv
    sys.argv = [str(source_path), *ctx.args]
    try:
        app_instance.serve(mode=mode, host=host, port=port)
    finally:
        sys.argv = original_argv
