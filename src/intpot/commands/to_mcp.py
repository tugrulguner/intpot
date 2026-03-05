"""Convert a source app to a FastMCP server."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.commands._convert import convert
from intpot.core.models import SourceType


def to_mcp(
    source: Path = typer.Argument(
        ..., help="Path to a source Python file or directory"
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output file or directory path"
    ),
) -> None:
    """Convert a CLI or API source to a FastMCP server."""
    convert(source, output, target=SourceType.MCP, label="MCP server", suffix="_mcp")
