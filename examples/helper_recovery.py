"""Recover plain helpers and immutable constants into standalone targets.

Run: uv run python examples/helper_recovery.py
Requires intpot[all] and the framework test clients used by this example.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import FastMCP
from typer.testing import CliRunner

import intpot

app = FastAPI()
FACTOR = 7


def multiply(value: int) -> int:
    return value * FACTOR


def scale(value: int) -> int:
    return multiply(value)


@app.get("/calc")
def calc(x: int) -> int:
    return scale(x)


def main() -> None:
    assert TestClient(app).get("/calc", params={"x": 3}).json() == 21
    loaded = intpot.load(Path(__file__))
    assert loaded.assess()["diagnostics"] == []
    assert loaded.schema.tools[0].support_definitions
    for target in ("cli", "mcp"):
        namespace: dict[str, Any] = {"__name__": "helper_example"}
        code = getattr(loaded, "to_" + target)()
        exec(compile(code, "<helper-example>", "exec", dont_inherit=True), namespace)
        if target == "cli":
            result = CliRunner().invoke(namespace["app"], ["3"])
            assert result.exit_code == 0, result.exception
            assert result.stdout == "21\n"
        else:
            response = asyncio.run(namespace["mcp"].call_tool("calc", {"x": 3}))
            assert response.content[0].text == "21"
        print(f"Generated {target}: calc(3) = 21")

    original_mcp = FastMCP("helper-example")
    original_mcp.tool()(calc)
    mcp_source = intpot.IntpotApp(intpot.SourceType.MCP, original_mcp)
    namespace = {"__name__": "helper_api_example"}
    exec(
        compile(mcp_source.to_api(), "<helper-api>", "exec", dont_inherit=True),
        namespace,
    )
    response = TestClient(namespace["app"]).post("/calc", json=3)
    assert response.status_code == 200, response.text
    assert response.json() == {"result": 21}
    print("Generated api: calc(3) = 21 (native result envelope)")


if __name__ == "__main__":
    main()
