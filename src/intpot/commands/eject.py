"""Export an intpot App as standalone framework code."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.commands.serve import _find_intpot_app


def eject_command(
    source: Path = typer.Argument(
        ..., help="Path to a Python file containing an intpot App"
    ),
    to: str = typer.Option(..., "--to", "-t", help="Target framework: cli, mcp, api"),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output file path (prints to stdout if omitted)"
    ),
) -> None:
    """Export an intpot App as standalone framework code."""
    from intpot.runtime import App

    source_path = Path(source).resolve()
    if not source_path.exists():
        typer.echo(f"Error: File not found: {source_path}", err=True)
        raise typer.Exit(1)

    app_instance = _find_intpot_app(source_path)
    assert isinstance(app_instance, App)

    try:
        code = app_instance.eject(target=to)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None

    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(code)
        typer.echo(f"Wrote {to} code to {out}", err=True)
    else:
        typer.echo(code)
