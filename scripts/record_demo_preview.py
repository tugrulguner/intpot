"""Record reproducible outputs from the shipped live Intpot interfaces."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from typer.testing import CliRunner

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "examples" / "semantic_schema.py"


def record() -> dict[str, Any]:
    """Exercise real CLI, FastAPI, and FastMCP adapters for the example app."""
    from intpot.runtime_builders import (
        build_fastapi_app,
        build_fastmcp_app,
        build_typer_app,
    )

    spec = importlib.util.spec_from_file_location("intpot_demo_source", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import example source: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = module.app
    examples = []
    for name, arguments in (
        ("Ada", {"name": "Ada", "excited": True}),
        ("Ada", {"name": "Ada", "excited": False}),
    ):
        cli_result = CliRunner().invoke(
            build_typer_app(app.name, app._tools),
            [name, "--excited"] if arguments["excited"] else [name],
        )
        if cli_result.exit_code:
            raise RuntimeError(
                f"Live CLI failed: {cli_result.exception}; {cli_result.output}; {cli_result.stderr}"
            )
        api_result = TestClient(
            cast(Any, build_fastapi_app(app.name, app._tools))
        ).post("/greet", json=arguments)
        if api_result.status_code != 200:
            raise RuntimeError(f"Live API failed: {api_result.text}")
        mcp_result = asyncio.run(
            build_fastmcp_app(app.name, app._tools).call_tool("greet", arguments)
        )
        if mcp_result.is_error:
            raise RuntimeError("Live MCP call failed")
        examples.append(
            {
                "id": "greet" if arguments["excited"] else "greet-plain",
                "title": "Greet with emphasis"
                if arguments["excited"]
                else "Greet plainly",
                "input": arguments,
                "interfaces": {
                    "cli": cli_result.stdout,
                    "api": api_result.json(),
                    "mcp": mcp_result.content[0].text,
                },
            }
        )
    version = importlib.metadata.version("intpot")
    return {
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "intpot_version": version,
        "execution": "live Intpot serve adapters exercised in-process",
        "interfaces": [
            "CLI (Typer)",
            "API (FastAPI TestClient)",
            "MCP (FastMCP call_tool)",
        ],
        "examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = record()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Recorded {len(payload['examples'])} examples to {args.output}")


if __name__ == "__main__":
    main()
