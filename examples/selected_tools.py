"""A useful slug command plus an ordinary callback-guarded command."""

from __future__ import annotations

import typer

app = typer.Typer()


def guarded_callback(value: str) -> str:
    if len(value) < 3:
        raise typer.BadParameter("value must contain at least three characters")
    return value


@app.command()
def slug(text: str) -> None:
    """Normalize whitespace in text into a lowercase hyphenated slug."""
    typer.echo("-".join(text.lower().split()))


@app.command()
def guarded(value: str = typer.Option(..., callback=guarded_callback)) -> None:
    """An ordinary callback-guarded command excluded from selected conversion."""
    typer.echo(value)


if __name__ == "__main__":
    app()
