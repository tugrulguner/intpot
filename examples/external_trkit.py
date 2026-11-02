"""Compare a pinned trkit slug CLI with generated HTTP and stdio MCP servers.

Install the unchanged upstream package first; see external-applications/trkit.md.
Only the selected slug workflow is qualified, not root options or the entire app.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import intpot

REVISION = "b86ef6464f514782b6643771cc73119174c7d4e1"
REPOSITORY = "https://github.com/ardazeybek-dev/trkit"
CASES: list[dict[str, str]] = [
    {"text_": "İstanbul IĞDIR çay"},
    {"text_": "İstanbul IĞDIR çay", "separator": "_"},
    {"text_": "Çığır Açan Şeyler!", "separator": "."},  # noqa: RUF001 - Turkish input
    {"text_": ""},
]
BAD_SEPARATOR = "\\g<missing>"


def native(
    arguments: list[str], output: Path, name: str
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "trkit.cli", *arguments],
        cwd=output,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    (output / f"{name}.stdout").write_text(result.stdout, encoding="utf-8")
    (output / f"{name}.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def call_http(script: Path) -> dict[str, Any]:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with script.with_suffix(".log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                f"{script.stem}:app",
                "--app-dir",
                str(script.parent),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(150):
                if server.poll() is not None:
                    raise RuntimeError("Generated server exited; inspect its log")
                try:
                    with urllib.request.urlopen(
                        base + "/openapi.json", timeout=0.2
                    ) as response:
                        schema = json.load(response)
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            else:
                raise TimeoutError("Generated HTTP server did not become ready")
            if set(schema["paths"]) != {"/slug"}:
                raise RuntimeError("Unexpected generated routes")

            def post(payload: dict[str, Any]) -> tuple[int, Any]:
                request = urllib.request.Request(
                    base + "/slug",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                try:
                    with urllib.request.urlopen(request, timeout=10) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code, error.read().decode()

            values = []
            for case in CASES:
                status, body = post(case)
                if status != 200:
                    raise RuntimeError(f"Valid slug request failed: {status}: {body}")
                values.append(body["result"])
            missing_status, _ = post({})
            wrong_type_status, _ = post({"text_": 123})
            error_status, _ = post({"text_": "a b", "separator": BAD_SEPARATOR})
            if (missing_status, wrong_type_status, error_status) != (422, 422, 500):
                raise RuntimeError("Unexpected HTTP validation/business-error behavior")
            return {
                "values": values,
                "missing_input_status": missing_status,
                "wrong_type_status": wrong_type_status,
                "business_error_status": error_status,
            }
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


async def call_mcp(script: Path) -> dict[str, Any]:
    from fastmcp import Client
    from fastmcp.client.transports import PythonStdioTransport

    async with Client(
        PythonStdioTransport(script, python_cmd=sys.executable)
    ) as client:
        listed = await client.list_tools()
        tools = [tool.name for tool in getattr(listed, "tools", listed)]
        if tools != ["slug"]:
            raise RuntimeError(f"Unexpected MCP tools: {tools}")
        values = []
        for case in CASES:
            result = await client.call_tool("slug", case)
            if getattr(result, "is_error", getattr(result, "isError", False)):
                raise RuntimeError("Valid MCP slug call failed")
            texts = [item.text for item in result.content if item.type == "text"]
            if len(texts) != 1:
                raise RuntimeError("Expected one slug text result")
            values.append(texts[0])
        rejections = []
        for payload in (
            {},
            {"text_": 123},
            {"text_": "a b", "separator": BAD_SEPARATOR},
        ):
            try:
                result = await client.call_tool("slug", payload)
            except Exception as error:
                from fastmcp.exceptions import ToolError

                if not isinstance(error, ToolError):
                    raise
                rejections.append(type(error).__name__)
            else:
                if not getattr(result, "is_error", getattr(result, "isError", False)):
                    raise RuntimeError("Invalid MCP input unexpectedly succeeded")
                rejections.append("error_result")
        return {"tools": tools, "values": values, "rejections": rejections}


def run(checkout: Path, output: Path) -> dict[str, Any]:
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if revision != REVISION:
        raise ValueError(f"Expected trkit revision {REVISION}, got {revision}")
    if subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain"],
        text=True,
    ).strip():
        raise ValueError("Use an unmodified trkit checkout")
    package = importlib.import_module("trkit")
    if package.__file__ is None:
        raise ValueError("Install trkit from the pinned checkout")
    installed = Path(package.__file__).parent
    source_root = checkout / "src" / "trkit"
    sources = sorted(source_root.rglob("*.py"))
    if not sources:
        raise ValueError("No source files found")
    for source in sources:
        if (
            source.read_bytes()
            != (installed / source.relative_to(source_root)).read_bytes()
        ):
            raise ValueError(f"Installed source differs: {source}")
    license_bytes = (checkout / "LICENSE").read_bytes()
    if b"MIT License" not in license_bytes:
        raise ValueError("Expected the pinned MIT license")
    output.mkdir(parents=True, exist_ok=False)
    values = []
    for index, case in enumerate(CASES):
        arguments = ["slug", case["text_"]]
        if "separator" in case:
            arguments += ["--separator", case["separator"]]
        result = native(arguments, output, f"case-{index}")
        if result.returncode != 0:
            raise RuntimeError(f"Original CLI failed: {result.stderr}")
        values.append(result.stdout.removesuffix("\n"))
    if values[:2] != ["istanbul-igdir-cay", "istanbul_igdir_cay"]:
        raise RuntimeError("Unexpected native Turkish slug results")
    missing = native(["slug"], output, "missing")
    business = native(
        ["slug", "a b", "--separator", BAD_SEPARATOR], output, "business-error"
    )
    if missing.returncode != 2 or business.returncode != 1:
        raise RuntimeError("Original CLI did not reject missing input/business error")
    module = importlib.import_module("trkit.cli")
    selected = intpot.load(module.app).select("slug")
    selected.write(str(output / "slug_api.py"), "api")
    selected.write(str(output / "slug_mcp.py"), "mcp")
    http = call_http(output / "slug_api.py")
    mcp = asyncio.run(call_mcp(output / "slug_mcp.py"))
    if http["values"] != values or mcp["values"] != values:
        raise RuntimeError("Generated results differ from the original CLI")
    report = {
        "repository": REPOSITORY,
        "revision": revision,
        "license": "MIT",
        "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
        "verified_python_files": len(sources),
        "original_values": values,
        "native_missing_exit": missing.returncode,
        "native_business_error_exit": business.returncode,
        "http": http,
        "mcp": mcp,
        "results_match": True,
        "input_mode": "imported framework instance",
        "full_application_conversion_verified": False,
        "limitations": [
            "Only slug; no root lifecycle/version controls",
            "Direct package-file loading is not qualified",
            "Original trkit package remains a runtime dependency",
            "No persistent file effects in this workflow",
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.source_checkout.resolve(), args.output_dir.resolve()), indent=2
        )
    )


if __name__ == "__main__":
    main()
