"""Call a standalone converted MCP example over a real stdio connection.

Run from the source checkout with all extras installed:
    python examples/call_converted_mcp.py batch '{"quantity": 3}'
    python examples/call_converted_mcp.py storage '{"size_gb": 100, "days": 30}'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

SERVERS = {
    "batch": ("batch_quote_to_mcp.py", "quote"),
    "storage": ("storage_quote_to_mcp.py", "storage_quote"),
}


async def call(example: str, arguments: dict[str, Any]) -> None:
    filename, tool = SERVERS[example]
    script = Path(__file__).with_name("conversions") / filename
    transport = PythonStdioTransport(script, python_cmd=sys.executable)
    async with Client(transport) as client:
        result = await client.call_tool(tool, arguments)
        for content in result.content:
            if content.type == "text":
                print(content.text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", choices=SERVERS)
    parser.add_argument("arguments", help="JSON object containing the tool arguments")
    args = parser.parse_args()
    try:
        arguments = json.loads(args.arguments)
    except json.JSONDecodeError as error:
        parser.error(str(error))
    if not isinstance(arguments, dict):
        parser.error("arguments must be a JSON object")
    asyncio.run(call(args.example, arguments))


if __name__ == "__main__":
    main()
