"""Compare the storage-cost HTTP service with its generated CLI and MCP tools.

Source checkout only (unreleased). Compares a shared finite numeric input domain,
not all coercions or validation kinds. Run with all extras and httpx installed.
"""

from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError
from typer.testing import CliRunner

import intpot

VALID = [
    {"size_gb": 1},
    {"size_gb": 100, "days": 30},
    {"size_gb": 10000, "days": 365, "replicas": 1},
]
INVALID = {
    "below_minimum": {"size_gb": 0},
    "above_maximum": {"size_gb": 10001},
    "invalid_days": {"size_gb": 100, "days": 0},
    "invalid_replicas": {"size_gb": 100, "replicas": 4},
    "invalid_type": {"size_gb": "bad"},
    "missing_required": {},
    "business_error": {"size_gb": 10000, "replicas": 3},
}


def cli_arguments(payload: dict[str, Any]) -> list[str]:
    arguments = [str(payload["size_gb"])] if "size_gb" in payload else []
    for key, value in payload.items():
        if key != "size_gb":
            arguments.extend(["--" + key.replace("_", "-"), str(value)])
    return arguments


def mcp_value(result: Any) -> dict[str, Any]:
    content = getattr(result, "content", result)
    assert len(content) == 1
    value = json.loads(content[0].text)
    assert isinstance(value, dict)
    return value


async def verify() -> dict[str, Any]:
    loaded = intpot.load(Path(__file__).with_name("storage_quote.py"))
    assert loaded.assess()["diagnostics"] == []
    namespaces: dict[str, dict[str, Any]] = {}
    for target in ("cli", "mcp"):
        namespace: dict[str, Any] = {}
        exec(
            compile(getattr(loaded, "to_" + target)(), f"<generated-{target}>", "exec"),
            namespace,
        )
        namespaces[target] = namespace
    runner = CliRunner()
    api = TestClient(loaded.app, raise_server_exceptions=False)
    output: dict[str, Any] = {}
    expected: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="intpot-storage-conformance-") as directory:
        root = Path(directory)
        async with Client(namespaces["mcp"]["mcp"]) as mcp:
            listed = await mcp.list_tools()
            tools = getattr(listed, "tools", listed)
            assert [tool.name for tool in tools] == ["storage_quote"]
            for interface in ("source_api", "cli", "mcp"):
                results = []
                rejected = {}
                for index, payload in enumerate(VALID):
                    receipt = root / f"{interface}-valid-{index}.txt"
                    call = {**payload, "receipt": str(receipt)}
                    if interface == "source_api":
                        response = api.get("/storage-quote", params=call)
                        assert response.status_code == 200, response.text
                        value = response.json()
                        expected.append(value)
                    elif interface == "cli":
                        result = runner.invoke(
                            namespaces["cli"]["app"], cli_arguments(call)
                        )
                        assert result.exit_code == 0, result.exception
                        value = ast.literal_eval(result.stdout)
                    else:
                        value = mcp_value(await mcp.call_tool("storage_quote", call))
                    assert value == expected[index]
                    assert (
                        ast.literal_eval(receipt.read_text(encoding="utf-8")) == value
                    )
                    results.append(value)
                for name, payload in INVALID.items():
                    receipt = root / f"{interface}-{name}.txt"
                    call = {**payload, "receipt": str(receipt)}
                    if interface == "source_api":
                        response = api.get("/storage-quote", params=call)
                        assert response.status_code == (
                            500 if name == "business_error" else 422
                        ), response.text
                        rejected[name] = response.status_code
                    elif interface == "cli":
                        result = runner.invoke(
                            namespaces["cli"]["app"], cli_arguments(call)
                        )
                        assert result.exit_code == (
                            1 if name == "business_error" else 2
                        ), result.output
                        if name == "business_error":
                            assert isinstance(result.exception, ValueError)
                        rejected[name] = result.exit_code
                    else:
                        try:
                            result = await mcp.call_tool("storage_quote", call)
                        except ToolError as error:
                            rejected[name] = type(error).__name__
                        else:
                            assert getattr(
                                result, "is_error", getattr(result, "isError", False)
                            ), result
                            rejected[name] = "tool_error"
                    assert not receipt.exists(), (interface, name)
                output[interface] = {
                    "valid_results": results,
                    "rejections": rejected,
                    "receipts_verified": True,
                }
    return {
        "business_scope": "API storage cost, native CLI/MCP consumers",
        "interfaces": output,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
