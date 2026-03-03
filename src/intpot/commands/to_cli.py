"""Convert a source app to a Typer CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.core.detector import detect_source
from intpot.core.models import SourceType


def to_cli(
    source: Path = typer.Argument(..., help="Path to the source Python file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Convert an MCP or API source to a Typer CLI app."""
    source_type, app_instance = detect_source(source)

    if source_type == SourceType.CLI:
        typer.echo("Source is already a Typer CLI app.", err=True)
        raise typer.Exit(1)

    if source_type == SourceType.MCP:
        from intpot.core.inspectors.mcp import MCPInspector

        inspector = MCPInspector()
    else:
        from intpot.core.inspectors.api import APIInspector

        inspector = APIInspector()

    tools = inspector.inspect(app_instance)

    from intpot.core.generators.cli import CLIGenerator

    code = CLIGenerator().generate(tools)

    if output:
        output.write_text(code)
        typer.echo(f"Generated CLI app: {output}")
    else:
        typer.echo(code)
