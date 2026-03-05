"""Shared conversion logic for CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from intpot.core.models import SourceType, ToolInfo


def inspect_app(source_type: SourceType, app_instance: Any) -> list[ToolInfo]:
    """Inspect an app instance and return normalized tool definitions."""
    if source_type == SourceType.MCP:
        from intpot.core.inspectors.mcp import MCPInspector

        return MCPInspector().inspect(app_instance)
    if source_type == SourceType.CLI:
        from intpot.core.inspectors.cli import CLIInspector

        return CLIInspector().inspect(app_instance)

    from intpot.core.inspectors.api import APIInspector

    return APIInspector().inspect(app_instance)


def convert(
    source: Path,
    output: Path | None,
    target: SourceType,
    label: str,
    suffix: str,
) -> None:
    """Shared conversion logic for all `intpot to *` commands.

    Args:
        source: Source file or directory.
        output: Output file or directory path (None for stdout).
        target: Target framework type (used to skip same-type sources).
        label: Human-readable label for output messages (e.g. "CLI app").
        suffix: File suffix for directory output (e.g. "_cli").
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
            (p, st, app) for p, st, app in discover_sources(source) if st != target
        ]
        if not sources:
            typer.echo("No convertible sources found.", err=True)
            raise typer.Exit(1)

        for file_path, source_type, app_instance in sources:
            tools = inspect_app(source_type, app_instance)
            code = generator.generate(tools)
            if output:
                output.mkdir(parents=True, exist_ok=True)
                out_file = output / f"{file_path.stem}{suffix}.py"
                out_file.write_text(code)
                typer.echo(f"Generated {label}: {out_file}")
            else:
                typer.echo(f"# --- {file_path.name} ---")
                typer.echo(code)
        return

    from intpot.core.detector import detect_source

    source_type, app_instance = detect_source(source)

    if source_type == target:
        typer.echo(f"Source is already a {label}.", err=True)
        raise typer.Exit(1)

    tools = inspect_app(source_type, app_instance)
    code = generator.generate(tools)

    if output:
        output.write_text(code)
        typer.echo(f"Generated {label}: {output}")
    else:
        typer.echo(code)
