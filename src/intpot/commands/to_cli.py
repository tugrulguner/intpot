"""Convert a source app to a Typer CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.core.detector import detect_source
from intpot.core.models import SourceType


def _inspect(source_type: SourceType, app_instance: object) -> list:
    if source_type == SourceType.MCP:
        from intpot.core.inspectors.mcp import MCPInspector

        return MCPInspector().inspect(app_instance)

    from intpot.core.inspectors.api import APIInspector

    return APIInspector().inspect(app_instance)


def to_cli(
    source: Path = typer.Argument(
        ..., help="Path to a source Python file or directory"
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output file or directory path"
    ),
) -> None:
    """Convert an MCP or API source to a Typer CLI app."""
    if source.is_dir():
        from intpot.core.discovery import discover_sources

        sources = [
            (p, st, app)
            for p, st, app in discover_sources(source)
            if st != SourceType.CLI
        ]
        if not sources:
            typer.echo("No convertible sources found.", err=True)
            raise typer.Exit(1)

        from intpot.core.generators.cli import CLIGenerator

        generator = CLIGenerator()
        for file_path, source_type, app_instance in sources:
            tools = _inspect(source_type, app_instance)
            code = generator.generate(tools)
            if output:
                output.mkdir(parents=True, exist_ok=True)
                out_file = output / f"{file_path.stem}_cli.py"
                out_file.write_text(code)
                typer.echo(f"Generated CLI app: {out_file}")
            else:
                typer.echo(f"# --- {file_path.name} ---")
                typer.echo(code)
        return

    source_type, app_instance = detect_source(source)

    if source_type == SourceType.CLI:
        typer.echo("Source is already a Typer CLI app.", err=True)
        raise typer.Exit(1)

    tools = _inspect(source_type, app_instance)

    from intpot.core.generators.cli import CLIGenerator

    code = CLIGenerator().generate(tools)

    if output:
        output.write_text(code)
        typer.echo(f"Generated CLI app: {output}")
    else:
        typer.echo(code)
