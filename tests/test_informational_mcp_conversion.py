from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from typer.testing import CliRunner

import intpot
from intpot.core.callbacks import UnsupportedCLIParameterCallbackError
from intpot.core.generators.mcp import MCPGenerator


def _is_error(result):
    if hasattr(result, "is_error"):
        return result.is_error
    return result.isError


@pytest.mark.parametrize("generation", ["builder", "projection", "write", "cli"])
def test_exclusive_information_mcp_keeps_flat_typed_calls(
    tmp_source, monkeypatch, generation, eager_callback_annotations
):
    path = tmp_source("""from enum import StrEnum
from pathlib import Path
import json
import typer

class Mode(StrEnum):
    MD="md"
    JSON="json"

def version_callback(value: bool):
    if value:
        print("VERSION")
        raise typer.Exit()

def logo_callback(value: bool):
    if value:
        print("LOGO")
        raise typer.Exit()

app=typer.Typer()
@app.command()
def convert(output: str, mode: Mode=typer.Option(Mode.MD), version: bool=typer.Option(False, callback=version_callback, is_eager=True), logo: bool=typer.Option(False, callback=logo_callback, is_eager=True)):
    Path(output).write_text(json.dumps({"mode":mode.value,"version":version,"logo":logo}))
    typer.echo("converted")
""")
    (path.parent / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(path.parent.parent))
    monkeypatch.setenv(
        "PYTHONPATH",
        str(path.parent.parent) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    loaded = intpot.load(path)
    native = CliRunner().invoke(loaded.app, ["--version", "--mode", "invalid"])
    assert native.exit_code == 0 and "VERSION" in native.output
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        loaded.to_mcp()
    with pytest.raises(ValueError, match="Unknown callback policy"):
        loaded.to_mcp(callback_policy="unknown")
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        loaded.to_mcp(allow_scaffold=True)
    target = path.parent / "generated_mcp.py"
    if generation == "builder":
        code = loaded.to_mcp(callback_policy="exclusive-informational")
    elif generation == "projection":
        projected = loaded.project("mcp", callback_policy="exclusive-informational")
        assert projected.callback_policy == "exclusive-informational"
        code = MCPGenerator().generate(projected)
    elif generation == "write":
        loaded.write(target, "mcp", callback_policy="exclusive-informational")
        code = target.read_text()
    else:
        conversion = subprocess.run(
            [
                sys.executable,
                str(Path(sys.executable).parent / "intpot"),
                "to",
                "mcp",
                str(path),
                "--callback-policy",
                "exclusive-informational",
                "-o",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert conversion.returncode == 0, (conversion.stdout, conversion.stderr)
        code = target.read_text()
    target.write_text(code)
    output = path.parent / "result.json"

    async def calls():
        transport = PythonStdioTransport(
            target, python_cmd=sys.executable, env=dict(os.environ)
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
            tools = getattr(tools, "tools", tools)
            tool = next(tool for tool in tools if tool.name == "convert")
            input_schema = getattr(tool, "input_schema", None)
            if input_schema is None:
                input_schema = tool.inputSchema
            assert "request" not in input_schema.get("properties", {})
            assert "anyOf" in input_schema or "oneOf" in input_schema
            normal = await client.call_tool(
                "convert", {"output": str(output), "mode": "md"}
            )
            assert not _is_error(normal)
            assert [item.text for item in normal.content] == ["converted"]
            assert json.loads(output.read_text()) == {
                "mode": "md",
                "version": None,
                "logo": None,
            }
            output.unlink()
            info = await client.call_tool(
                "convert", {"version": True, "mode": "invalid"}
            )
            assert not _is_error(info)
            assert [item.text for item in info.content] == ["VERSION\n"]
            assert not output.exists()
            for arguments in (
                {"version": True, "logo": True},
                {"output": str(output), "mode": "invalid"},
                {"version": "true"},
            ):
                from mcp.shared import exceptions as sdk_errors

                sdk_error = getattr(sdk_errors, "MCPError", None) or sdk_errors.McpError
                try:
                    options: dict[str, Any] = (
                        {"raise_on_error": False}
                        if "raise_on_error"
                        in inspect.signature(client.call_tool).parameters
                        else {}
                    )
                    rejected = await client.call_tool("convert", arguments, **options)
                except sdk_error as error:
                    detail = getattr(error, "error", error)
                    assert detail.code == -32602, str(error)
                else:
                    assert _is_error(rejected)
                assert not output.exists()

    asyncio.run(calls())
    assert all(
        parameter.unsupported_callback
        for parameter in loaded.schema.tools[0].parameters
        if parameter.informational_callback
    )
