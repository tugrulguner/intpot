"""Shared conversion logic for CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from intpot.converter import (
    UnsupportedFastAPIDependencyError,
    tools_for_target,
)
from intpot.core.models import SourceType


def _mirrored_destination(
    file_path: Path,
    source_root: Path,
    output: Path | None,
    suffix: str,
) -> Path:
    """Where one discovered source's output belongs, mirroring the source tree.

    Only the filename changes; the directories between the scanned root and the
    source are preserved. Naming outputs after the basename alone meant
    `alpha/tools.py` and `beta/tools.py` both wrote `tools_mcp.py`, and the
    second silently replaced the first.
    """
    # discover_sources resolves the directory it scans and yields absolute
    # paths, so the root has to be resolved too or relative_to raises.
    relative = file_path.resolve().relative_to(source_root.resolve())
    mirrored = relative.parent / f"{relative.stem}{suffix}.py"
    return (output / mirrored) if output else mirrored


def _plan_destinations(
    sources: list[tuple[Path, SourceType, object]],
    source_root: Path,
    output: Path | None,
    suffix: str,
) -> list[Path]:
    """Resolve every destination before writing any of them.

    Mirroring makes the source-to-destination mapping injective, so a collision
    here means an assumption broke rather than a project being unusual. Either
    way, finding out before the first write beats finding out after the last.
    """
    destinations = [
        _mirrored_destination(file_path, source_root, output, suffix)
        for file_path, _, _ in sources
    ]

    claimed: dict[Path, Path] = {}
    for (file_path, _, _), destination in zip(sources, destinations, strict=True):
        previous = claimed.get(destination)
        if previous is not None:
            typer.echo(
                f"Refusing to write: {previous} and {file_path} both map to "
                f"{destination}. Please report this — mirroring the source tree "
                f"is meant to make that impossible.",
                err=True,
            )
            raise typer.Exit(1)
        claimed[destination] = file_path

    return destinations


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

        # Every destination is resolved up front, and dry-run reports exactly
        # the paths a real run would write.
        destinations = _plan_destinations(sources, source, output, suffix)

        planned: list[tuple[Path, Path, str]] = []
        for (file_path, source_type, app_instance), destination in zip(
            sources, destinations, strict=True
        ):
            try:
                tools = tools_for_target(source_type, app_instance, target)
            except UnsupportedFastAPIDependencyError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(1) from None
            planned.append((file_path, destination, generator.generate(tools)))

        for file_path, destination, code in planned:
            if dry_run:
                typer.echo(f"# --- Would generate: {destination} ---")
                typer.echo(code)
            elif output:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(code)
                typer.echo(f"Generated {label}: {destination}")
            else:
                # The relative path, not the basename: two `tools.py` in
                # different packages are indistinguishable otherwise.
                relative = file_path.resolve().relative_to(source.resolve())
                typer.echo(f"# --- {relative} ---")
                typer.echo(code)
        return

    from intpot.core.detector import DetectionError, detect_source

    if verbose:
        print(f"Detecting: {source}", file=sys.stderr)

    try:
        source_type, app_instance = detect_source(source)
    except DetectionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if verbose:
        print(f"FOUND: {source} ({source_type.value})", file=sys.stderr)

    if source_type == target:
        typer.echo(f"Source is already a {label}.", err=True)
        raise typer.Exit(1)

    try:
        tools = tools_for_target(source_type, app_instance, target)
    except UnsupportedFastAPIDependencyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    code = generator.generate(tools)

    if dry_run:
        out_path = output or Path(f"{source.stem}{suffix}.py")
        typer.echo(f"# --- Would generate: {out_path} ---")
        typer.echo(code)
    elif output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(code)
        typer.echo(f"Generated {label}: {output}")
    else:
        typer.echo(code)
