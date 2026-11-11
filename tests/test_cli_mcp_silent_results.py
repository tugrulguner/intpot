"""Silent CLI commands must not execute successfully then fail MCP result validation."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from typer.testing import CliRunner

import intpot


@pytest.mark.parametrize("ending", ["return", "return None"])
def test_silent_return_preserves_nested_none_and_api_response(
    tmp_path: Path, ending: str
) -> None:
    source = tmp_path / "nested_cli.py"
    source.write_text(
        """from pathlib import Path
import typer
app = typer.Typer()
@app.command()
def create(output: str, stop: bool = False, fail: bool = False) -> None:
    if fail:
        raise ValueError("rejected before effects")
    if stop:
        return
    def helper():
        return None
    class Local:
        def value(self):
            return None
    previous = Path(output).read_text() if Path(output).exists() else ""
    Path(output).write_text(previous + str((helper() is None, Local().value() is None)))
    ENDING
""".replace("ENDING", ending)
    )
    app = intpot.load(source)
    native_path = tmp_path / "native.txt"
    native = CliRunner().invoke(app.app, [str(native_path)])
    assert native.exit_code == 0 and native.stdout == ""
    assert native_path.read_text() == "(True, True)"
    namespace: dict[str, Any] = {"__name__": "api_none"}
    exec(compile(app.to_api(), "api_none.py", "exec"), namespace)
    with TestClient(namespace["app"]) as client:
        response = client.post("/create", json={"output": str(tmp_path / "http.txt")})
        assert response.status_code == 200
        assert response.json() == (
            {"result": None} if ending == "return None" else None
        )
    generated = tmp_path / "nested_server.py"
    generated.write_text(app.to_mcp())
    destination = tmp_path / "mcp.txt"

    async def call() -> None:
        async with Client(
            PythonStdioTransport(
                generated, python_cmd=sys.executable, env=dict(os.environ)
            )
        ) as client:
            for flags in ({}, {"stop": True}):
                path = destination if not flags else tmp_path / "stopped.txt"
                result = await client.call_tool(
                    "create", {"output": str(path), **flags}
                )
                assert not result.is_error and result.structured_content == {
                    "result": ""
                }
                if flags:
                    assert not path.exists()
            rejected = tmp_path / "rejected.txt"
            result = await client.call_tool(
                "create", {"output": str(rejected), "fail": True}, raise_on_error=False
            )
            assert result.is_error and not rejected.exists()

    asyncio.run(call())
    assert destination.read_bytes() == native_path.read_bytes()


def test_silent_cli_file_effect_returns_valid_empty_mcp_text(tmp_path: Path) -> None:
    source = tmp_path / "source_cli.py"
    source.write_text("""from pathlib import Path
import typer
app = typer.Typer()
@app.command()
def create(output: str) -> None:
    Path(output).write_text("created once")
""")
    app = intpot.load(source)
    native_path = tmp_path / "native.txt"
    native = CliRunner().invoke(app.app, [str(native_path)])
    assert native.exit_code == 0 and native.stdout == ""
    generated = tmp_path / "silent_server.py"
    generated.write_text(app.to_mcp())
    target = tmp_path / "mcp.txt"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    async def call() -> None:
        async with Client(
            PythonStdioTransport(generated, python_cmd=sys.executable, env=env)
        ) as client:
            result = await client.call_tool("create", {"output": str(target)})
            assert not result.is_error
            assert result.structured_content == {"result": ""}

    asyncio.run(call())
    assert target.read_bytes() == native_path.read_bytes()


@pytest.mark.parametrize("ending", ["return", "return None"])
def test_suppressed_context_exit_reaches_valid_mcp_fallthrough(
    tmp_path: Path, ending: str
) -> None:
    source = tmp_path / "context_exit_cli.py"
    source.write_text(
        """from pathlib import Path
from contextlib import suppress
import typer
app = typer.Typer()
@app.command()
def create(output: str, fail: bool = False) -> None:
    if fail:
        raise ValueError("unhandled before effects")
    class ExitFailure:
        def __enter__(self):
            return None
        def __exit__(self, *args):
            raise ValueError("exit failed")
    with suppress(ValueError):
        with ExitFailure():
            ENDING
    previous = Path(output).read_text() if Path(output).exists() else ""
    Path(output).write_text(previous + "created once")
""".replace("ENDING", ending)
    )
    app = intpot.load(source)
    native_path = tmp_path / "native.txt"
    native = CliRunner().invoke(app.app, [str(native_path)])
    assert native.exit_code == 0 and native.stdout == ""
    assert native_path.read_text() == "created once"
    native_error = tmp_path / "native-error.txt"
    rejected = CliRunner().invoke(app.app, [str(native_error), "--fail"])
    assert rejected.exit_code != 0 and not native_error.exists()
    generated = tmp_path / "context_exit_server.py"
    generated.write_text(app.to_mcp())
    destination = tmp_path / "mcp.txt"

    async def call() -> None:
        async with Client(
            PythonStdioTransport(
                generated, python_cmd=sys.executable, env=dict(os.environ)
            )
        ) as client:
            result = await client.call_tool("create", {"output": str(destination)})
            assert not result.is_error
            assert result.structured_content == {"result": ""}
            error_path = tmp_path / "mcp-error.txt"
            result = await client.call_tool(
                "create",
                {"output": str(error_path), "fail": True},
                raise_on_error=False,
            )
            assert result.is_error and not error_path.exists()

    asyncio.run(call())
    assert destination.read_bytes() == native_path.read_bytes()
