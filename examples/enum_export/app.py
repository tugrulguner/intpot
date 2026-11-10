"""Export a UTF-8 text file as plain text or escaped HTML."""

from __future__ import annotations

import html
from enum import StrEnum
from pathlib import Path

import typer


class OutputFormat(StrEnum):
    TEXT = "text"
    HTML = "html"


app = typer.Typer()


@app.command()
def export(
    source: str,
    output: str,
    to: list[OutputFormat] = typer.Option(None, "--to"),
) -> None:
    """Write a plain-text or HTML export; repeat --to to select formats."""
    content = Path(source).read_text(encoding="utf-8")
    # Bodies receive enum members; consume their values without recovering a class.
    formats = [item.value for item in to] if to else ["text"]
    outputs: list[str] = []
    for output_format in formats:
        target = Path(output).with_suffix(
            ".html" if output_format == "html" else ".txt"
        )
        rendered = (
            f"<pre>{html.escape(content)}</pre>\n"
            if output_format == "html"
            else content
        )
        target.write_text(rendered, encoding="utf-8")
        outputs.append(str(target))
    typer.echo("Wrote " + ", ".join(outputs))


if __name__ == "__main__":
    app()
