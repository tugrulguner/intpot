"""Inspectable CLI validation that Intpot deliberately refuses to export.

Run the original validation:
    uv run python examples/callback_cli.py --name Camila
    uv run python examples/callback_cli.py --name Rick  # rejected
Inspect the callback marker:
    uv run intpot inspect examples/callback_cli.py --json
Conversion intentionally refuses rather than dropping validation:
    uv run intpot to api examples/callback_cli.py
    uv run intpot to mcp examples/callback_cli.py
"""

from __future__ import annotations

import typer

app = typer.Typer()


def validate_name(value: str) -> str:
    if value != "Camila":
        raise typer.BadParameter("Only Camila is allowed")
    return value.upper()


@app.command()
def greet(name: str = typer.Option(..., callback=validate_name)) -> None:
    """Greet the name after validation and normalization."""
    typer.echo(f"Hello {name}")


if __name__ == "__main__":
    app()
