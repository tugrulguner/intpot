"""Shared conversion logic for CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from intpot.converter import inspect_app
from intpot.core.models import SourceType
from intpot.core.transforms import transform_tools


def convert(
    source: Path,
    output: Path | None,
    target: SourceType,
    label: str,
    suffix: str,
    *,
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    """Shared conversion logic for all `intpot to *` commands.

    Args:
        source: Source file or directory.
        output: Output file or directory path (None for stdout).
        target: Target framework type (used to skip same-type sources).
        label: Human-readable label for output messages (e.g. "CLI app").
        suffix: File suffix for directory output (e.g. "_cli").
        verbose: Print discovery/detection details to stderr.
        dry_run: Print generated code to stdout without writing files.
    """
    from intpot.core.generators.api import APIGenerator
    from intpot.core.generators.cli import CLIGenerator
    from intpot.core.generators.mcp import MCPGenerator

    generators = {
        SourceType.CLI: CLIGenerator,
        SourceType.MCP: MCPGenerator,
        SourceType.API: APIGenerator,
    }
    generator = generators[target]()

    if source.is_dir():
        from intpot.core.discovery import discover_sources

        sources = [
            (p, st, app)
            for p, st, app in discover_sources(source, verbose=verbose)
            if st != target
        ]
        if not sources:
            typer.echo("No convertible sources found.", err=True)
            raise typer.Exit(1)

        for file_path, source_type, app_instance in sources:
            tools = inspect_app(source_type, app_instance)
            tools = transform_tools(tools, source_type, target)
            code = generator.generate(tools)

            if dry_run:
                out_path = (
                    (output / f"{file_path.stem}{suffix}.py")
                    if output
                    else Path(f"{file_path.stem}{suffix}.py")
                )
                typer.echo(f"# --- Would generate: {out_path} ---")
                typer.echo(code)
            elif output:
                output.mkdir(parents=True, exist_ok=True)
                out_file = output / f"{file_path.stem}{suffix}.py"
                out_file.write_text(code)
                typer.echo(f"Generated {label}: {out_file}")
            else:
                typer.echo(f"# --- {file_path.name} ---")
                typer.echo(code)
        return

    from intpot.core.detector import detect_source

    if verbose:
        print(f"Detecting: {source}", file=sys.stderr)

    source_type, app_instance = detect_source(source)

    if verbose:
        print(f"FOUND: {source} ({source_type.value})", file=sys.stderr)

    if source_type == target:
        typer.echo(f"Source is already a {label}.", err=True)
        raise typer.Exit(1)

    tools = inspect_app(source_type, app_instance)
    tools = transform_tools(tools, source_type, target)
    code = generator.generate(tools)

    if dry_run:
        out_path = output or Path(f"{source.stem}{suffix}.py")
        typer.echo(f"# --- Would generate: {out_path} ---")
        typer.echo(code)
    elif output:
        output.write_text(code)
        typer.echo(f"Generated {label}: {output}")
    else:
        typer.echo(code)
