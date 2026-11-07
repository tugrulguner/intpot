"""A native Typer file converter; Intpot is deliberately not a dependency."""

from __future__ import annotations

import html
from enum import StrEnum
from pathlib import Path

import typer


class OutputFormat(StrEnum):
    HTML = "html"
    TEXT = "text"


def version_callback(value: bool):
    if value:
        print("informational-text 1.0")
        raise typer.Exit()


def formats_callback(value: bool):
    if value:
        print("html, text")
        raise typer.Exit()


app = typer.Typer()


@app.command()
def convert(
    source: str,
    output: str,
    format: OutputFormat = typer.Option(OutputFormat.HTML),
    version: bool = typer.Option(False, callback=version_callback, is_eager=True),
    formats: bool = typer.Option(False, callback=formats_callback, is_eager=True),
):
    """Convert a UTF-8 text file to escaped HTML or copy its text."""
    text = Path(source).read_text(encoding="utf-8")
    if format.value == "html":
        text = "<pre>" + html.escape(text) + "</pre>\n"
    Path(output).write_text(text, encoding="utf-8")
    typer.echo(f"Wrote {output}")


if __name__ == "__main__":
    app()
