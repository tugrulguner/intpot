"""Convert a source app to a FastAPI app."""

from __future__ import annotations

from pathlib import Path

import typer

from intpot.commands._convert import convert
from intpot.core.models import SourceType


def to_api(
    source: Path = typer.Argument(
        ..., help="Path to a source Python file or directory"
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output file or directory path"
    ),
) -> None:
    """Convert a CLI or MCP source to a FastAPI app."""
    convert(source, output, target=SourceType.API, label="FastAPI app", suffix="_api")
