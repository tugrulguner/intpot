"""Convert a source app to a Typer CLI."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.commands._convert import convert
from intpot.core.models import SourceType


def to_cli(
    source: Path = typer.Argument(
        ..., help="Path to a source Python file or directory"
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output file or directory path"
    ),
) -> None:
    """Convert an MCP or API source to a Typer CLI app."""
    convert(source, output, target=SourceType.CLI, label="CLI app", suffix="_cli")
