"""Execute a real bounded-order CLI and its generated CLI, HTTP and MCP consumers.

Requires the unreleased numeric-range source slice; public v0.16.0 lacks this guarantee.
Run: uv run --all-extras --with httpx python examples/application_conformance.py
Native error/transport formats differ. This compares a bounded shared input domain,
business results, default omission, and receipt side effects, not Python equivalence.
"""

from __future__ import annotations

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
    (dict(quantity=1), 25),
    (dict(quantity=3), 75),
    (dict(quantity=10, discount=25), 225),
]
INVALID = {
    "below_minimum": dict(quantity=0),
    "above_maximum": dict(quantity=11),
    "negative_discount": dict(quantity=3, discount=-1),
    "invalid_type": dict(quantity="bad"),
    "business_error": dict(quantity=1, discount=26),
}


def normalized_result(value: Any) -> int:
    if hasattr(value, "content"):
        value = value.content
    if isinstance(value, list):
        assert len(value) == 1
        value = value[0].text
    if isinstance(value, dict):
        assert set(value) == {"result"}
        value = value["result"]
    if isinstance(value, str):
        value = json.loads(value)
    assert isinstance(value, int) and not isinstance(value, bool), value
    return value


def arguments(payload: dict[str, Any]) -> list[str]:
    return [part for key, value in payload.items() for part in ("--" + key, str(value))]


async def verify() -> dict[str, Any]:
    loaded = intpot.load(Path(__file__).with_name("batch_quote.py"))
    assert loaded.assess()["diagnostics"] == []
    namespaces: dict[str, dict[str, Any]] = {}
    for target in ("cli", "api", "mcp"):
        namespace: dict[str, Any] = {}
        if target == "cli":
            # Public same-source conversion deliberately refuses. Exercise its
            # existing low-level renderer separately, not an invented to_cli path.
            from intpot.core.generators.cli import CLIGenerator

            code = CLIGenerator().generate(loaded.schema)
        else:
            code = getattr(loaded, "to_" + target)()
        exec(compile(code, f"<generated-{target}>", "exec"), namespace)
        namespaces[target] = namespace
    runner = CliRunner()
    api = TestClient(namespaces["api"]["app"], raise_server_exceptions=False)
    output: dict[str, Any] = {}
    with TemporaryDirectory(prefix="intpot-order-conformance-") as directory:
        root = Path(directory)
        async with Client(namespaces["mcp"]["mcp"]) as mcp:
            tool_result = await mcp.list_tools()
            tools = getattr(tool_result, "tools", tool_result)
            assert [tool.name for tool in tools] == ["quote"]
            for interface in ("source_cli", "generated_cli", "api", "mcp"):
                values: list[int] = []
                rejections: dict[str, Any] = {}
                for index, (payload, expected) in enumerate(VALID):
                    receipt = root / f"{interface}-valid-{index}.txt"
                    call = {**payload, "receipt": str(receipt)}
                    if interface in ("source_cli", "generated_cli"):
                        app = (
                            loaded.app
                            if interface == "source_cli"
                            else namespaces["cli"]["app"]
                        )
                        result = runner.invoke(app, arguments(call))
                        assert result.exit_code == 0, result.exception
                        value = normalized_result(result.stdout)
                    elif interface == "api":
                        response = api.post("/quote", json=call)
                        assert response.status_code == 200, response.text
                        value = normalized_result(response.json())
                    else:
                        value = normalized_result(await mcp.call_tool("quote", call))
                    assert value == expected
                    assert receipt.read_text(encoding="utf-8") == str(expected)
                    values.append(value)
                for name, payload in INVALID.items():
                    receipt = root / f"{interface}-{name}.txt"
                    call = {**payload, "receipt": str(receipt)}
                    if interface in ("source_cli", "generated_cli"):
                        app = (
                            loaded.app
                            if interface == "source_cli"
                            else namespaces["cli"]["app"]
                        )
                        result = runner.invoke(app, arguments(call))
                        if name == "business_error":
                            assert result.exit_code == 1 and isinstance(
                                result.exception, ValueError
                            )
                        else:
                            assert result.exit_code == 2, result.output
                        rejections[name] = result.exit_code
                    elif interface == "api":
                        response = api.post("/quote", json=call)
                        assert response.status_code == (
                            500 if name == "business_error" else 422
                        ), response.text
                        rejections[name] = response.status_code
                    else:
                        try:
                            result = await mcp.call_tool("quote", call)
                        except ToolError as error:
                            rejections[name] = type(error).__name__
                        else:
                            assert getattr(
                                result, "is_error", getattr(result, "isError", False)
                            ), result
                            rejections[name] = "tool_error"
                    assert not receipt.exists(), (interface, name)
                output[interface] = {
                    "valid_results": values,
                    "rejections": rejections,
                    "receipts_verified": True,
                }
    return {
        "business_scope": "bounded CLI quote, native generated interfaces",
        "interfaces": output,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
