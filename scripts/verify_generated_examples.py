"""Execute checked-in generated examples through their real frameworks."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient
from typer.testing import CliRunner

ROOT = Path(__file__).parents[1]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load example module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_generated_cli() -> None:
    module = _load_module(
        "intpot_generated_advanced_cli",
        ROOT / "examples" / "conversions" / "advanced_api_to_cli.py",
    )
    result = CliRunner().invoke(module.app, ["get-user", "7"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == (
        "{'user_id': '7', 'username': 'example', 'role': 'member'}\n"
    )
    print("verified generated CLI command")


def verify_generated_mcp() -> None:
    module = _load_module(
        "intpot_generated_advanced_mcp",
        ROOT / "examples" / "conversions" / "advanced_api_to_mcp.py",
    )
    result = asyncio.run(module.mcp.call_tool("get_user", {"user_id": "7"}))
    assert result.is_error is False
    assert result.structured_content == {
        "user_id": "7",
        "username": "example",
        "role": "member",
    }
    print("verified generated MCP tool")


def verify_dependency_api() -> None:
    module = _load_module(
        "intpot_dependency_api",
        ROOT / "examples" / "dependency_api.py",
    )
    response = TestClient(module.app).get("/profile")
    assert response.status_code == 200
    assert response.json() == {"username": "example", "role": "member"}
    print("verified dependency FastAPI route")


def main() -> None:
    verify_generated_cli()
    verify_generated_mcp()
    verify_dependency_api()


if __name__ == "__main__":
    main()
