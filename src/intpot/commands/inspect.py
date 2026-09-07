"""Inspect extracted tools without converting."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from intpot.converter import compile_app
from intpot.core.inspectors.base import InspectionError
from intpot.core.models import SourceType


def _schema_or_exit(
    source_type: SourceType,
    app_instance: object,
    *,
    source_path: Path,
):
    try:
        return compile_app(source_type, app_instance, source_path=source_path)
    except (InspectionError, TypeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None


def _params_summary(params):
    parts = []
    for p in params:
        s = f"{p.name}: {p.type_annotation}"
        if not p.required:
            s += f"={p.default!r}"
        parts.append(s)
    joined = ", ".join(parts)
    if len(joined) > 40:
        joined = joined[:37] + "..."
    return joined


def inspect_command(
    source: Path = typer.Argument(
        ..., help="Path to a source Python file or directory"
    ),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Print detection details to stderr"
    ),
) -> None:
    """Display extracted tools/endpoints without generating code."""
    if source.is_dir():
        from intpot.core.discovery import discover_sources

        sources = list(discover_sources(source, verbose=verbose))
        if not sources:
            typer.echo("No sources found.", err=True)
            raise typer.Exit(1)

        all_results = []
        for file_path, source_type, app_instance in sources:
            schema = _schema_or_exit(
                source_type,
                app_instance,
                source_path=file_path,
            )
            all_results.append((file_path, schema))

        if as_json:
            out = []
            for file_path, schema in all_results:
                out.append(
                    {
                        "source": str(file_path),
                        "type": schema.source_type.value,
                        "tools": [tool.to_dict() for tool in schema.tools],
                    }
                )
            typer.echo(json.dumps(out, indent=2, default=str))
            return

        for file_path, schema in all_results:
            _print_table(file_path, schema.source_type, schema.tools)
        return

    from intpot.core.detector import DetectionError, detect_source

    if verbose:
        print(f"Detecting: {source}", file=sys.stderr)

    try:
        source_type, app_instance = detect_source(source)
    except DetectionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None

    if verbose:
        print(f"FOUND: {source} ({source_type.value})", file=sys.stderr)

    schema = _schema_or_exit(source_type, app_instance, source_path=source)

    if as_json:
        out = [
            {
                "source": str(source),
                "type": schema.source_type.value,
                "tools": [tool.to_dict() for tool in schema.tools],
            }
        ]
        typer.echo(json.dumps(out, indent=2, default=str))
        return

    _print_table(source, schema.source_type, schema.tools)


def _print_table(source: Path, source_type: SourceType, tools):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print(f"\nSource: {source} ({source_type.value})")

    if not tools:
        console.print("[dim]No tools found.[/dim]")
        return

    table = Table(show_header=True)
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Parameters")
    table.add_column("Return Type")
    table.add_column("Async")

    for t in tools:
        table.add_row(
            t.name,
            t.description or "",
            _params_summary(t.parameters),
            t.return_type,
            "Yes" if t.is_async else "No",
        )

    console.print(table)
