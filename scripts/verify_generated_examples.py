"""Execute checked-in generated examples through their real frameworks."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from contextlib import redirect_stdout
from io import StringIO
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
    result = CliRunner().invoke(module.app, ["get_user", "7"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == (
        "{'user_id': '7', 'username': 'example', 'role': 'member'}\n"
    )
    created = CliRunner().invoke(
        module.app,
        ["create_user", "ada", "ada@example.com"],
    )
    assert created.exit_code == 0, created.exception
    assert created.stdout == (
        "{'username': 'ada', 'email': 'ada@example.com', 'role': 'member', "
        "'created': True, 'status': 201}\n"
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
    created = asyncio.run(
        module.mcp.call_tool(
            "create_user",
            {"username": "ada", "email": "ada@example.com"},
        )
    )
    assert created.is_error is False
    assert created.structured_content == {
        "username": "ada",
        "email": "ada@example.com",
        "role": "member",
        "created": True,
        "status": 201,
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


def verify_generated_cli_to_api() -> None:
    basic = _load_module(
        "intpot_generated_cli_to_api",
        ROOT / "examples" / "conversions" / "cli_to_api.py",
    )
    greeted = TestClient(basic.app).post(
        "/greet", json={"name": "Ada", "greeting": "Hi"}
    )
    assert greeted.status_code == 200, greeted.text
    assert greeted.json() == {"result": "Hi, Ada!"}

    advanced = _load_module(
        "intpot_generated_advanced_cli_to_api",
        ROOT / "examples" / "conversions" / "advanced_cli_to_api.py",
    )
    searched = TestClient(advanced.app).post(
        "/search", json={"query": "alias", "include-done": True}
    )
    assert searched.status_code == 200, searched.text
    assert len(json.loads(searched.json()["result"])) == 2
    print("verified generated CLI-to-API parameter aliases")


def verify_semantic_schema() -> None:
    module = _load_module(
        "intpot_semantic_schema",
        ROOT / "examples" / "semantic_schema.py",
    )
    schema = module.app.schema
    payload = schema.to_dict()
    assert payload["name"] == "schema-example"
    assert payload["source_type"] == "python"
    assert [tool["name"] for tool in payload["tools"]] == ["greet"]
    assert [parameter["name"] for parameter in payload["tools"][0]["parameters"]] == [
        "name",
        "excited",
    ]
    print("verified semantic schema example")


def verify_missing_binding() -> None:
    module = _load_module(
        "intpot_missing_binding", ROOT / "examples" / "missing_binding.py"
    )
    response = TestClient(module.app).get("/calc", params={"x": 3})
    assert response.status_code == 200
    assert response.json() == 21
    output = StringIO()
    with redirect_stdout(output):
        module.main()
    assert "calc(3) = 21" in output.getvalue()
    assert "Cannot convert tools with missing bindings" in output.getvalue()
    print("verified missing-binding diagnostics and refusal example")


def verify_helper_recovery() -> None:
    module = _load_module(
        "intpot_helper_recovery", ROOT / "examples" / "helper_recovery.py"
    )
    output = StringIO()
    with redirect_stdout(output):
        module.main()
    assert "Generated cli: calc(3) = 21" in output.getvalue()
    assert "Generated mcp: calc(3) = 21" in output.getvalue()
    assert "Generated api: calc(3) = 21" in output.getvalue()
    print("verified bounded helper recovery through CLI API and MCP")


def verify_definition_bindings() -> None:
    module = _load_module(
        "intpot_definition_bindings", ROOT / "examples" / "definition_bindings.py"
    )
    output = StringIO()
    with redirect_stdout(output):
        module.main()
    assert output.getvalue().splitlines() == [
        "Original HTTP API: /value = 1",
        "cli: missing_annotation_binding names=['Model']",
        "mcp: missing_definition_binding names=['Model']",
        "CLI and MCP conversion refused before writing, including scaffold opt-in",
    ]
    print("verified definition-binding diagnostics and before-write refusal")
    context = _load_module(
        "intpot_diagnostic_context", ROOT / "examples" / "diagnostic_context.py"
    )
    output = StringIO()
    with redirect_stdout(output):
        context.main()
    diagnostics = json.loads(output.getvalue())
    assert {item["code"] for item in diagnostics} == {
        "missing_annotation_binding",
        "missing_definition_binding",
    }
    assert all(
        item["source_location"] is None
        and item["references"]
        and "Model" in item["suggested_action"]
        for item in diagnostics
    )
    print("verified actionable diagnostic context and before-write refusal")


def main() -> None:
    verify_generated_cli()
    verify_generated_mcp()
    verify_dependency_api()
    verify_generated_cli_to_api()
    verify_semantic_schema()
    verify_missing_binding()
    verify_helper_recovery()
    verify_definition_bindings()


if __name__ == "__main__":
    main()
