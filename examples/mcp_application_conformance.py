"""Compare original inventory MCP with generated CLI and HTTP consumers.

Source checkout only (unreleased). Shared finite numeric inputs, not universal
coercion or wire-format equivalence. Native errors keep their framework formats.
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

VALID = [{"quantity": 1}, {"quantity": 25, "packs": 3}, {"quantity": 100}]
INVALID = {
    "below_minimum": {"quantity": 0},
    "above_maximum": {"quantity": 101},
    "invalid_packs": {"quantity": 10, "packs": 6},
    "invalid_type": {"quantity": "bad"},
    "missing_required": {},
    "business_error": {"quantity": 100, "packs": 2},
}


def cli_arguments(payload: dict[str, Any]) -> list[str]:
    arguments = [str(payload["quantity"])] if "quantity" in payload else []
    for key, value in payload.items():
        if key != "quantity":
            arguments.extend(["--" + key.replace("_", "-"), str(value)])
    return arguments


def mcp_value(result: Any) -> dict[str, Any]:
    content = getattr(result, "content", result)
    assert len(content) == 1
    value = json.loads(content[0].text)
    assert isinstance(value, dict)
    return value


async def verify() -> dict[str, Any]:
    loaded = intpot.load(Path(__file__).with_name("inventory_reservation.py"))
    assert loaded.assess()["diagnostics"] == []
    namespaces: dict[str, dict[str, Any]] = {}
    for target in ("cli", "api"):
        namespace: dict[str, Any] = {}
        exec(
            compile(getattr(loaded, "to_" + target)(), f"<generated-{target}>", "exec"),
            namespace,
        )
        namespaces[target] = namespace
    api = TestClient(namespaces["api"]["app"], raise_server_exceptions=False)
    route = loaded.project("api").tools[0].route_path
    assert route
    runner = CliRunner()
    expected: list[dict[str, Any]] = []
    output: dict[str, Any] = {}
    with TemporaryDirectory(prefix="intpot-inventory-conformance-") as directory:
        root = Path(directory)
        async with Client(loaded.app) as mcp:
            listed = await mcp.list_tools()
            tools = getattr(listed, "tools", listed)
            assert [tool.name for tool in tools] == ["reserve_inventory"]
            for interface in ("source_mcp", "cli", "api"):
                results = []
                rejected = {}
                for index, payload in enumerate(VALID):
                    receipt = root / f"{interface}-valid-{index}.txt"
                    call = {**payload, "receipt": str(receipt)}
                    if interface == "source_mcp":
                        value = mcp_value(
                            await mcp.call_tool("reserve_inventory", call)
                        )
                        expected.append(value)
                    elif interface == "cli":
                        result = runner.invoke(
                            namespaces["cli"]["app"], cli_arguments(call)
                        )
                        assert result.exit_code == 0, result.exception
                        value = ast.literal_eval(result.stdout)
                    else:
                        response = api.post(route, json=call)
                        assert response.status_code == 200, response.text
                        value = response.json()
                    assert value == expected[index]
                    assert (
                        ast.literal_eval(receipt.read_text(encoding="utf-8")) == value
                    )
                    results.append(value)
                for name, payload in INVALID.items():
                    receipt = root / f"{interface}-{name}.txt"
                    call = {**payload, "receipt": str(receipt)}
                    if interface == "source_mcp":
                        try:
                            result = await mcp.call_tool("reserve_inventory", call)
                        except ToolError as error:
                            if name == "business_error":
                                assert "reservation exceeds available stock" in str(
                                    error
                                )
                            rejected[name] = type(error).__name__
                        else:
                            assert getattr(
                                result, "is_error", getattr(result, "isError", False)
                            ), result
                            rejected[name] = "tool_error"
                    elif interface == "cli":
                        result = runner.invoke(
                            namespaces["cli"]["app"], cli_arguments(call)
                        )
                        assert result.exit_code == (
                            1 if name == "business_error" else 2
                        ), result.output
                        if name == "business_error":
                            assert isinstance(result.exception, ValueError)
                            assert (
                                str(result.exception)
                                == "reservation exceeds available stock"
                            )
                        rejected[name] = result.exit_code
                    else:
                        response = api.post(route, json=call)
                        assert response.status_code == (
                            500 if name == "business_error" else 422
                        ), response.text
                        rejected[name] = response.status_code
                    assert not receipt.exists(), (interface, name)
                output[interface] = {
                    "valid_results": results,
                    "rejections": rejected,
                    "receipts_verified": True,
                }
    return {
        "business_scope": "MCP inventory reservation, native CLI/HTTP consumers",
        "interfaces": output,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
