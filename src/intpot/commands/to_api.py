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
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print detection details to stderr"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview output without writing files"
    ),
    allow_scaffold: bool = typer.Option(
        False,
        "--allow-scaffold",
        help="Emit explicit NotImplementedError scaffolds for missing bodies",
    ),
) -> None:
    """Convert a CLI or MCP source to a FastAPI app."""
    convert(
        source,
        output,
        target=SourceType.API,
        label="FastAPI app",
        suffix="_api",
        verbose=verbose,
        dry_run=dry_run,
        allow_scaffold=allow_scaffold,
    )
