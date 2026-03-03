"""Scaffold a new intpot project."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer

_SCAFFOLD_DIR = Path(__file__).resolve().parent.parent / "templates" / "scaffold"


class ProjectType(str, Enum):
    mcp = "mcp"
    cli = "cli"
    api = "api"


def init_command(
    name: str = typer.Argument(..., help="Project name"),
    project_type: ProjectType = typer.Option(
        ..., "--type", "-t", help="Project type: mcp, cli, or api"
    ),
) -> None:
    """Scaffold a new project (FastMCP / Typer / FastAPI)."""
    target_dir = Path.cwd() / name
    if target_dir.exists():
        typer.echo(f"Directory '{name}' already exists.", err=True)
        raise typer.Exit(1)

    template_dir = _SCAFFOLD_DIR / project_type.value
    target_dir.mkdir(parents=True)

    for template_file in template_dir.iterdir():
        if template_file.is_file():
            content = template_file.read_text()
            content = content.replace("{{project_name}}", name)
            (target_dir / template_file.name).write_text(content)

    typer.echo(f"Created {project_type.value} project: {target_dir}")
