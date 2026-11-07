"""Run native CLI, generated loopback HTTP and generated stdio MCP workflows.

Run from a source checkout with all extras installed:
    uv run --no-sync python examples/informational_application_conformance.py
Artifacts remain in the printed directory. Files are server-local, not uploads.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

import intpot

POLICY = "exclusive-informational"
VERSION = "informational-text 1.0\n"


def http_request(base: str, route: str, payload: dict[str, Any] | None = None):
    request = urllib.request.Request(
        base + route,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


async def run_mcp(
    script: Path, source: Path, output: Path, env: dict[str, str], expected: str
):
    transport = PythonStdioTransport(script, python_cmd=sys.executable, env=env)
    async with Client(transport) as client:
        tools = await client.list_tools()
        tool = next(tool for tool in tools if tool.name == "convert")
        schema = getattr(tool, "input_schema", None)
        if schema is None:
            schema = tool.inputSchema
        (script.parent / "mcp-input-schema.json").write_text(
            json.dumps(schema, indent=2)
        )
        normal = await client.call_tool(
            "convert", {"source": str(source), "output": str(output)}
        )
        assert not normal.is_error and output.read_bytes() == expected.encode("utf-8")
        normal_text = [getattr(item, "text", None) for item in normal.content]
        assert normal_text == [f"Wrote {output}"]
        info_output = output.with_name("mcp-info-must-not-exist.html")
        info = await client.call_tool(
            "convert",
            {"version": True, "format": "invalid", "output": str(info_output)},
        )
        info_text = [getattr(item, "text", None) for item in info.content]
        assert not info.is_error and info_text == [VERSION] and not info_output.exists()
        from mcp.shared import exceptions as sdk_errors

        sdk_error = getattr(sdk_errors, "MCPError", None) or sdk_errors.McpError
        try:
            conflict = await client.call_tool(
                "convert", {"version": True, "formats": True}, raise_on_error=False
            )
        except sdk_error as error:
            assert getattr(error, "error", error).code == -32602
        else:
            assert conflict.is_error
        assert not info_output.exists()
        return {"normal": normal_text, "version": info_text, "conflict_rejected": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = args.output_dir or Path(
        tempfile.mkdtemp(prefix="intpot-informational-example-")
    )
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    examples = Path(__file__).resolve().parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(examples) + os.pathsep + env.get("PYTHONPATH", "")
    source = root / "input.txt"
    text = "Curiosity & <science>\n"
    source.write_text(text)
    expected = "<pre>" + html.escape(text) + "</pre>\n"
    native_output = root / "native.html"
    cli = [sys.executable, "-m", "informational_text.app"]
    native = subprocess.run(
        [*cli, str(source), str(native_output)],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert native.returncode == 0 and native_output.read_bytes() == expected.encode(
        "utf-8"
    ), native.stderr
    native_info = subprocess.run(
        [*cli, "--version", "--format", "invalid"],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert native_info.returncode == 0 and native_info.stdout == VERSION, (
        native_info.stderr
    )
    app = intpot.load(examples / "informational_text" / "app.py")
    api = root / "generated_api.py"
    mcp = root / "generated_mcp.py"
    api.write_text(app.to_api(callback_policy=POLICY))
    mcp.write_text(app.to_mcp(callback_policy=POLICY))
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    api_output = root / "http.html"
    with (root / "http-server.log").open("w") as log:
        process = subprocess.Popen(
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
            cwd=root,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 15
            while True:
                try:
                    status, schema = http_request(base, "/openapi.json")
                    if status == 200:
                        break
                except urllib.error.URLError:
                    pass
                if process.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError(
                        "HTTP readiness failed; inspect http-server.log"
                    )
                time.sleep(0.05)
            (root / "http-openapi.json").write_text(json.dumps(schema, indent=2))
            status, ordinary = http_request(
                base, "/convert", {"source": str(source), "output": str(api_output)}
            )
            assert status == 200 and api_output.read_bytes() == expected.encode(
                "utf-8"
            ), ordinary
            status, information = http_request(
                base, "/convert", {"version": True, "format": "invalid"}
            )
            assert status == 200 and information == {"result": VERSION}, information
            conflict_output = root / "must-not-exist.html"
            status, _ = http_request(
                base,
                "/convert",
                {"version": True, "formats": True, "output": str(conflict_output)},
            )
            assert status == 422 and not conflict_output.exists()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    mcp_output = root / "mcp.html"
    mcp_result = asyncio.run(run_mcp(mcp, source, mcp_output, env, expected))
    report = {
        "scope": "purpose-built runnable example, not an external-application qualification",
        "policy": POLICY,
        "source_parameters": len(app.schema.tools[0].parameters),
        "cli": {"normal": native.stdout, "version": native_info.stdout},
        "http": {"normal": ordinary, "version": information, "conflict_rejected": True},
        "mcp": mcp_result,
        "html": expected,
        "source_callback_markers_retained": all(
            p.unsupported_callback
            for p in app.schema.tools[0].parameters
            if p.informational_callback
        ),
    }
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"artifacts": str(root), **report}, indent=2))


if __name__ == "__main__":
    main()
