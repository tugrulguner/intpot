from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import typer
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from typer.main import get_command
from typer.testing import CliRunner

from intpot import load


def test_typer029_type_descriptor_uses_registered_inspection(monkeypatch):
    app = typer.Typer()

    @app.command()
    def greet(count: int = typer.Option(1, min=1, max=3)) -> str:
        return str(count)

    native = get_command(app)
    param = next(p for p in native.params if p.name == "count")
    if hasattr(param, "type"):
        # The locked Typer floor still uses Click's native parameter API.
        return
    assert type(param.type_descriptor).__name__ == "TypeDescriptor"

    from intpot.core.inspectors.cli import CLIInspector

    inspector = CLIInspector()
    called = False
    original = inspector._extract_registered_app

    def registered(*args, **kwargs):
        nonlocal called
        called = True
        return original(*args, **kwargs)

    monkeypatch.setattr(inspector, "_extract_registered_app", registered)
    tools = inspector.inspect(app)
    assert called
    assert tools and tools[0].parameters[0].name == "count"


def test_public_load_and_schema_with_typer029_native_control():
    app = typer.Typer()

    @app.command()
    def greet(count: int = typer.Option(1, min=1, max=3)) -> str:
        return str(count)

    native = get_command(app)
    assert any(p.name == "count" for p in native.params)
    loaded = load(app)
    assert loaded.schema.tools
    assert loaded.schema.tools[0].parameters[0].name == "count"


def test_native_descriptor_consumers_preserve_types_defaults_and_effects(
    tmp_path: Path,
) -> None:
    package = tmp_path / ("native_compat_" + uuid4().hex)
    package.mkdir()
    (package / "__init__.py").write_text("")
    path = package / "app.py"
    path.write_text("""from enum import StrEnum
from pathlib import Path
from typing import Optional
import json
import typer
class Mode(StrEnum):
    A = "a"
    B = "b"
app = typer.Typer()
@app.command()
def convert(output: str, quantity: int = typer.Option(2, min=1, max=3), modes: Optional[list[Mode]] = typer.Option(None, "--mode"), enabled: bool = typer.Option(False, "--enabled/--no-enabled")):
    result = {"quantity": quantity, "modes": None if modes is None else [item.value for item in modes], "enabled": enabled}
    Path(output).write_text(json.dumps(result))
    typer.echo(json.dumps(result))
""")
    loaded = load(path)
    parameters = loaded.schema.tools[0].parameters
    assert {p.name for p in parameters} == {"output", "quantity", "modes", "enabled"}
    quantity = next(p for p in parameters if p.name == "quantity")
    assert quantity.minimum == 1 and quantity.maximum == 3
    generated: dict[str, Any] = {"__name__": "descriptor_api"}
    exec(compile(loaded.to_api(), "descriptor_api.py", "exec"), generated)
    mcp_file = tmp_path / "generated_mcp.py"
    mcp_file.write_text(loaded.to_mcp())
    native_output = tmp_path / "native.json"
    api_output = tmp_path / "api.json"
    mcp_output = tmp_path / "mcp.json"
    native_results = []
    for tokens in (
        [],
        ["--quantity", "3", "--mode", "b", "--mode", "a", "--mode", "b", "--enabled"],
    ):
        native = CliRunner().invoke(loaded.app, [str(native_output), *tokens])
        assert native.exit_code == 0, native.exception
        native_results.append(native_output.read_bytes())
    with TestClient(generated["app"]) as client:
        for index, fields in enumerate(
            ({}, {"quantity": 3, "mode": ["b", "a", "b"], "enabled": True})
        ):
            response = client.post(
                "/convert", json={"output": str(api_output), **fields}
            )
            assert response.status_code == 200, response.text
            assert api_output.read_bytes() == native_results[index]
        for invalid in ({"quantity": 0}, {"mode": ["wrong"]}):
            bad = tmp_path / "invalid.json"
            response = client.post("/convert", json={"output": str(bad), **invalid})
            assert response.status_code == 422 and not bad.exists()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)

    async def calls() -> None:
        async with Client(
            PythonStdioTransport(mcp_file, python_cmd=sys.executable, env=env)
        ) as client:
            for index, fields in enumerate(
                ({}, {"quantity": 3, "modes": ["b", "a", "b"], "enabled": True})
            ):
                result = await client.call_tool(
                    "convert", {"output": str(mcp_output), **fields}
                )
                assert not result.is_error
                assert mcp_output.read_bytes() == native_results[index]
            for invalid in ({"quantity": 0}, {"modes": ["wrong"]}):
                bad = tmp_path / "invalid.json"
                result = await client.call_tool(
                    "convert", {"output": str(bad), **invalid}, raise_on_error=False
                )
                assert result.is_error and not bad.exists()

    asyncio.run(calls())
