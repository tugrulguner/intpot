"""Inspect extracted tools without converting."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import typer

from intpot.converter import inspect_app
from intpot.core.models import SourceType


def _serialize_tool(tool):
    d = asdict(tool)
    for p_info, p_dict in zip(tool.parameters, d["parameters"], strict=True):
        p_dict["required"] = p_info.required
        if p_info.required:
            del p_dict["default"]
    return d


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
            tools = inspect_app(source_type, app_instance)
            all_results.append((file_path, source_type, tools))

        if as_json:
            out = []
            for file_path, source_type, tools in all_results:
                out.append(
                    {
                        "source": str(file_path),
                        "type": source_type.value,
                        "tools": [_serialize_tool(t) for t in tools],
                    }
                )
            typer.echo(json.dumps(out, indent=2, default=str))
            return

        for file_path, source_type, tools in all_results:
            _print_table(file_path, source_type, tools)
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

    tools = inspect_app(source_type, app_instance)

    if as_json:
        out = [
            {
                "source": str(source),
                "type": source_type.value,
                "tools": [_serialize_tool(t) for t in tools],
            }
        ]
        typer.echo(json.dumps(out, indent=2, default=str))
        return

    _print_table(source, source_type, tools)


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
