"""Convert a source app to a FastMCP server."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.core.detector import detect_source
from intpot.core.models import SourceType


def to_mcp(
    source: Path = typer.Argument(..., help="Path to the source Python file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Convert a CLI or API source to a FastMCP server."""
    source_type, app_instance = detect_source(source)

    if source_type == SourceType.MCP:
        typer.echo("Source is already a FastMCP server.", err=True)
        raise typer.Exit(1)

    if source_type == SourceType.CLI:
        from intpot.core.inspectors.cli import CLIInspector

        inspector = CLIInspector()
    else:
        from intpot.core.inspectors.api import APIInspector

        inspector = APIInspector()

    tools = inspector.inspect(app_instance)

    from intpot.core.generators.mcp import MCPGenerator

    code = MCPGenerator().generate(tools)

    if output:
        output.write_text(code)
        typer.echo(f"Generated MCP server: {output}")
    else:
        typer.echo(code)
