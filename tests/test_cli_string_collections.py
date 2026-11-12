"""String collection conversion must preserve actual native CLI values."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from fastmcp.exceptions import ToolError
from typer.testing import CliRunner

import intpot


def test_required_string_inputs_and_repeatable_labels_reach_http_as_lists(
    tmp_path: Path,
) -> None:
    source = tmp_path / "manifest.py"
    source.write_text("""import json
from pathlib import Path
import typer
app = typer.Typer()
@app.command()
def manifest(source: list[str], output: str = typer.Option(...), label: list[str] = typer.Option(None, "--label")):
    record = {"sources": source, "labels": label, "count": len(source)}
    Path(output).write_text(json.dumps(record))
    typer.echo("manifest written")
""")
    app = intpot.load(source)
    native_file = tmp_path / "native.json"
    native = CliRunner().invoke(
        app.app,
        [
            "one.html",
            "two.html",
            "--output",
            str(native_file),
            "--label",
            "alpha",
            "--label",
            "beta",
            "--label",
            "alpha",
        ],
    )
    assert native.exit_code == 0, native.exception
    expected = json.loads(native_file.read_text())
    assert expected == {
        "sources": ["one.html", "two.html"],
        "labels": ["alpha", "beta", "alpha"],
        "count": 2,
    }
    namespace: dict[str, Any] = {"__name__": "manifest_http"}
    exec(compile(app.to_api(), "manifest_http.py", "exec"), namespace)
    destination = tmp_path / "http.json"
    with TestClient(namespace["app"]) as client:
        response = client.post(
            "/manifest",
            json={
                "source": ["one.html", "two.html"],
                "label": ["alpha", "beta", "alpha"],
                "output": str(destination),
            },
        )
    assert response.status_code == 200, response.text
    assert json.loads(destination.read_text()) == expected


@pytest.mark.parametrize("fallback", [False, True])
def test_required_variadic_string_list_rejects_empty_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallback: bool
) -> None:
    source = tmp_path / "required.py"
    source.write_text("""from pathlib import Path
import typer
app = typer.Typer()
@app.command()
def manifest(source: list[str], output: str = typer.Option(...)):
    Path(output).write_text(str(len(source)))
    typer.echo("written")
""")
    app = intpot.load(source)
    native_file = tmp_path / "native-empty.txt"
    native = CliRunner().invoke(app.app, ["--output", str(native_file)])
    assert native.exit_code != 0 and not native_file.exists()
    fallback_calls: list[bool] = []
    if fallback:

        def fail_tree() -> None:
            fallback_calls.append(True)
            raise RuntimeError("force registered fallback")

        monkeypatch.setattr(app.app, "_get_command", fail_tree, raising=False)
    namespace: dict[str, Any] = {"__name__": "required_http"}
    exec(compile(app.to_api(), "required_http.py", "exec"), namespace)
    if fallback:
        assert fallback_calls
    destination = tmp_path / "http-empty.txt"
    with TestClient(namespace["app"]) as client:
        response = client.post(
            "/manifest", json={"source": [], "output": str(destination)}
        )
    assert response.status_code == 422, response.text
    assert not destination.exists()


def test_required_string_list_stdio_mcp_validation_precedes_file_effect(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_manifest.py"
    source.write_text("""import json
from pathlib import Path
import typer
app = typer.Typer()
@app.command()
def manifest(source: list[str], output: str = typer.Option(...), label: list[str] = typer.Option(None, "--label")):
    Path(output).write_text(json.dumps({"sources": source, "labels": label}))
    typer.echo("manifest written")
""")
    server = tmp_path / "manifest_mcp_server.py"
    intpot.load(source).write(server, "mcp")

    async def exercise() -> None:
        transport = PythonStdioTransport(server, python_cmd=sys.executable)
        async with Client(transport) as client:
            destination = tmp_path / "mcp.json"
            result = await client.call_tool(
                "manifest",
                {
                    "source": ["a", "b", "a"],
                    "label": ["x", "x"],
                    "output": str(destination),
                },
            )
            assert not result.is_error
            assert json.loads(destination.read_text()) == {
                "sources": ["a", "b", "a"],
                "labels": ["x", "x"],
            }
            for index, invalid in enumerate([[], "a", [1], None]):
                rejected = tmp_path / f"rejected-{index}.json"
                with pytest.raises(ToolError):
                    await client.call_tool(
                        "manifest", {"source": invalid, "output": str(rejected)}
                    )
                assert not rejected.exists()

    asyncio.run(exercise())


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("target", ["api", "mcp"])
def test_environment_backed_string_lists_refuse_before_scaffold_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallback: bool, target: str
) -> None:
    source = tmp_path / "environment_manifest.py"
    source.write_text("""import json
from pathlib import Path
import typer
app = typer.Typer()
@app.command()
def manifest(output: str, label: list[str] = typer.Option(None, "--label", envvar="MANIFEST_LABELS")):
    Path(output).write_text(json.dumps(label))
    typer.echo("written")
""")
    app = intpot.load(source)
    native_file = tmp_path / "native-environment.json"
    native = CliRunner().invoke(
        app.app, [str(native_file)], env={"MANIFEST_LABELS": "alpha beta alpha"}
    )
    assert native.exit_code == 0, native.exception
    assert json.loads(native_file.read_text()) == ["alpha", "beta", "alpha"]
    if fallback:

        def fail_tree() -> None:
            raise RuntimeError("force registered fallback")

        monkeypatch.setattr(app.app, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "not-created" / "server.py"
    with pytest.raises(TypeError, match=r"[Ss]tring.list|collection"):
        app.write(destination, target, allow_scaffold=True)
    assert not destination.parent.exists()
