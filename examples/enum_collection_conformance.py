"""Run a repeatable enum option through native CLI, generated CLI, HTTP and stdio MCP.

This synthetic package exercises Docling-like --to semantics, not Docling conversion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import intpot
from intpot.core.generators.cli import CLIGenerator

SOURCE = """from pathlib import Path
import json
import typer
from .modes import Mode
app=typer.Typer()
@app.command()
def run(output:str, modes:list[Mode]=typer.Option(None,'--to')):
    value=None if modes is None else [mode.value for mode in modes]
    Path(output).write_text(json.dumps(value))
    typer.echo(json.dumps(value))
if __name__ == '__main__':
    app()
"""


def run(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    package = output / "enum_collection_demo"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "modes.py").write_text(
        "from enum import Enum\nclass Mode(str,Enum):\n MD='md'\n JSON='json'\n"
    )
    source = package / "cli.py"
    source.write_text(SOURCE)
    sys.path.insert(0, str(output))
    environment = {**os.environ, "PYTHONPATH": str(output)}
    environment.pop("PYTHONHOME", None)
    effect = output / "effect.json"
    cases = [
        ([], None),
        (["md"], ["md"]),
        (["md", "json"], ["md", "json"]),
        (["json", "md", "json"], ["json", "md", "json"]),
    ]
    report: dict[str, Any] = {
        "fixture": "Synthetic repeatable-enum CLI, not Docling conversion",
        "python": sys.executable,
        "native_cli": [],
        "generated_cli": [],
        "http": [],
        "mcp": [],
        "transport_boundary": "CLI omission follows installed Typer (None or []); explicit HTTP/MCP [] is an empty list. HTTP null follows installed FastAPI type/default behavior; nonnullable MCP null rejects.",
    }

    def cli(label: str, prefix: list[str]) -> None:
        for values, expected in cases:
            argv = [
                *prefix,
                str(effect),
                *[part for value in values for part in ("--to", value)],
            ]
            result = subprocess.run(
                argv,
                cwd=output,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            assert json.loads(effect.read_text()) == expected
            effect.unlink()
            report[label].append(
                {"argv": argv, "exit": result.returncode, "result": expected}
            )
        result = subprocess.run(
            [*prefix, str(effect), "--to", "md", "--to", "invalid"],
            cwd=output,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0 and not effect.exists()
        report[label].append(
            {"invalid_exit": result.returncode, "effect_exists": False}
        )

    native_prefix = [sys.executable, "-m", "enum_collection_demo.cli"]
    omitted = subprocess.run(
        [*native_prefix, str(effect)],
        cwd=output,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert omitted.returncode == 0, omitted.stderr
    native_default = json.loads(effect.read_text())
    assert native_default is None or native_default == []
    effect.unlink()
    cases[0] = ([], native_default)
    report["native_omitted_value"] = native_default
    cli("native_cli", native_prefix)
    app = intpot.load(source)
    (output / "generated_cli.py").write_text(CLIGenerator().generate(app.schema))
    app.write(output / "generated_api.py", "api")
    app.write(output / "generated_mcp.py", "mcp")
    cli("generated_cli", [sys.executable, str(output / "generated_cli.py")])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with (output / "http.log").open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "generated_api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=output,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("HTTP server exited; see http.log")
                try:
                    with urllib.request.urlopen(url + "/openapi.json", timeout=1):
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("HTTP startup timed out")
            for values, expected in cases:
                body: dict[str, Any] = {"output": str(effect)}
                if values:
                    body["to"] = values
                request = urllib.request.Request(
                    url + "/run",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    assert response.status == 200
                    assert json.loads(json.loads(response.read())["result"]) == expected
                assert json.loads(effect.read_text()) == expected
                effect.unlink()
                report["http"].append({"input": body, "result": expected})
            request = urllib.request.Request(
                url + "/run",
                data=json.dumps(
                    {"output": str(effect), "to": ["md", "invalid"]}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(request, timeout=10)
            except urllib.error.HTTPError as error:
                assert error.code == 422 and not effect.exists()
                report["http"].append({"invalid_status": 422, "effect_exists": False})
            else:
                raise AssertionError("Invalid member was admitted")
        finally:
            server.terminate()
            server.wait(timeout=15)

    async def mcp() -> None:
        from fastmcp import Client
        from fastmcp.client.transports import PythonStdioTransport
        from fastmcp.exceptions import ToolError

        async with Client(
            PythonStdioTransport(output / "generated_mcp.py", python_cmd=sys.executable)
        ) as client:
            for values, expected in cases:
                body: dict[str, Any] = {"output": str(effect)}
                if values:
                    body["modes"] = values
                result = await client.call_tool("run", body)
                assert json.loads(result.content[0].text) == expected
                assert json.loads(effect.read_text()) == expected
                effect.unlink()
                report["mcp"].append({"input": body, "result": expected})
            try:
                rejected = await client.call_tool(
                    "run", {"output": str(effect), "modes": ["md", "invalid"]}
                )
            except ToolError:
                assert not effect.exists()
                report["mcp"].append({"invalid_rejected": True, "effect_exists": False})
            else:
                assert getattr(
                    rejected, "is_error", getattr(rejected, "isError", False)
                )
                assert not effect.exists()
                report["mcp"].append({"invalid_rejected": True, "effect_exists": False})

    asyncio.run(mcp())
    report["verified"] = True
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(run(options.output_dir.resolve()), indent=2))
