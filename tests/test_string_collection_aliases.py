from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from typer.testing import CliRunner

import intpot
from intpot.core.generators.cli import CLIGenerator


@pytest.mark.parametrize("fallback", [False, True])
def test_list_and_optional_source_bindings_survive_collection_annotations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallback: bool
) -> None:
    source = tmp_path / "alias_manifest.py"
    source.write_text("""from typing import List as Seq, Optional as Maybe
import typer
app = typer.Typer()
def list(value: str) -> str:
    return value.upper()
def Optional(value: str) -> str:
    return "label:" + value
@app.command()
def manifest(label: Maybe[Seq[str]] = typer.Option(None, "--label")):
    typer.echo(Optional(list("none")) if label is None else Optional("|".join(label)))
""")
    loaded = intpot.load(source)
    native = CliRunner().invoke(loaded.app, ["--label", "a", "--label", "a"])
    assert native.exit_code == 0, native.exception
    expected = native.output.strip()
    calls: list[bool] = []
    if fallback:

        def fail_tree() -> None:
            calls.append(True)
            raise RuntimeError("force registered fallback")

        monkeypatch.setattr(loaded.app, "_get_command", fail_tree, raising=False)
    cli: dict[str, Any] = {"__name__": "alias_cli"}
    exec(CLIGenerator().generate(loaded.schema), cli)
    generated = CliRunner().invoke(cli["app"], ["--label", "a", "--label", "a"])
    assert generated.exit_code == 0, generated.exception
    assert generated.output.strip() == expected
    if fallback:
        assert calls
    api: dict[str, Any] = {"__name__": "alias_api"}
    exec(loaded.to_api(), api)
    with TestClient(api["app"]) as client:
        response = client.post("/manifest", json=["a", "a"])
        assert response.status_code == 200, response.text
        assert response.json() == {"result": expected}
    mcp: dict[str, Any] = {"__name__": "alias_mcp"}
    exec(loaded.to_mcp(), mcp)

    async def exercise() -> None:
        async with Client(mcp["mcp"]) as client:
            result = await client.call_tool("manifest", {"label": ["a", "a"]})
            assert not result.is_error
            assert any(
                content.type == "text" and content.text == expected
                for content in result.content
            )

    asyncio.run(exercise())
