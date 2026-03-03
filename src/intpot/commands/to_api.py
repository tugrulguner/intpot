"""Convert a source app to a FastAPI app."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.core.detector import detect_source
from intpot.core.models import SourceType


def to_api(
    source: Path = typer.Argument(..., help="Path to the source Python file"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Convert a CLI or MCP source to a FastAPI app."""
    source_type, app_instance = detect_source(source)

    if source_type == SourceType.API:
        typer.echo("Source is already a FastAPI app.", err=True)
        raise typer.Exit(1)

    if source_type == SourceType.MCP:
        from intpot.core.inspectors.mcp import MCPInspector

        inspector = MCPInspector()
    else:
        from intpot.core.inspectors.cli import CLIInspector

        inspector = CLIInspector()

    tools = inspector.inspect(app_instance)

    from intpot.core.generators.api import APIGenerator

    code = APIGenerator().generate(tools)

    if output:
        output.write_text(code)
        typer.echo(f"Generated FastAPI app: {output}")
    else:
        typer.echo(code)
