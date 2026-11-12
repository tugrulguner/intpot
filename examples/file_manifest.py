"""Write a content manifest from ordered, repeatable CLI inputs.

Source-checkout example (plain string-list conversion is unreleased).
Run from the repository root after installing all extras::

    uv run --no-sync python examples/file_manifest.py first.txt 'second file.txt' first.txt \
        --output manifest.json --label release --label 'A B' --label release

Inputs are local paths on the process/server filesystem, not uploaded files.
Every input is read before the manifest is written. Duplicate paths and labels
are deliberately retained. No authentication or public filesystem sandbox is
provided; run generated servers only against trusted local inputs.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import typer

app = typer.Typer()


@app.command()
def manifest(
    source: list[str],
    output: str = typer.Option(..., "--output"),
    label: list[str] = typer.Option(None, "--label"),
) -> None:
    """Record paths, byte lengths, SHA-256 digests, and optional labels."""
    files: list[dict[str, object]] = []
    for name in source:
        content = Path(name).read_bytes()
        files.append(
            {"path": name, "bytes": len(content), "sha256": sha256(content).hexdigest()}
        )
    record = {"files": files, "labels": label, "count": len(files)}
    Path(output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Manifest written for {len(files)} inputs")


if __name__ == "__main__":
    app()
