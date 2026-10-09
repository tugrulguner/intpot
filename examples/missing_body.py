"""Missing source is inspectable but cannot be exported as a working program.

    uv run python examples/missing_body.py
    uv run intpot inspect examples/missing_body.py --json
    uv run intpot to cli examples/missing_body.py  # refuses
    uv run intpot to cli examples/missing_body.py --allow-scaffold --dry-run

The source tool works. Its dynamically created implementation has no recoverable
source file; the opted-in generated scaffold fails until implemented.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastmcp import FastMCP

import intpot

mcp = FastMCP("missing-body")
exec("@mcp.tool()\ndef greet() -> str:\n    return 'Hello from the source'\n")

if __name__ == "__main__":
    loaded = intpot.load(mcp)
    print(json.dumps(loaded.assess(), indent=2))
    print(asyncio.run(mcp.call_tool("greet", {})).content[0].text)
    try:
        loaded.to_cli()
    except intpot.MissingFunctionBodyError as exc:
        print(f"Refused: {exc}")
    namespace: dict[str, Any] = {"__name__": "generated_scaffold"}
    exec(compile(loaded.to_cli(allow_scaffold=True), "<scaffold>", "exec"), namespace)
    from typer.testing import CliRunner

    result = CliRunner().invoke(namespace["app"], [])
    assert isinstance(result.exception, NotImplementedError), result.exception
    print(result.exception)
