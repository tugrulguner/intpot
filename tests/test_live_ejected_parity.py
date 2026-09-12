"""Behavioral parity between live and ejected ``intpot.App`` interfaces."""

from __future__ import annotations

import asyncio
import json
from types import ModuleType
from typing import Any

from typer.testing import CliRunner

from intpot import App
from intpot.runtime_builders import (
    build_fastapi_app,
    build_fastmcp_app,
    build_typer_app,
)


def _parity_app() -> App:
    app = App("parity-app")

    @app.tool(name="say_hi", description="Welcome someone.")
    async def greet(name: str, punctuation: str = "!") -> str:
        return f"Hello, {name}{punctuation}"

    @app.tool(description="Always fail.")
    def fail(message: str = "boom") -> str:
        raise ValueError(message)

    app._tools[0].info.parameters[0].description = "Person to welcome."
    return app


def _untyped_app() -> App:
    app = App("untyped-app")

    @app.tool()
    def classify(value):
        return f"{type(value).__name__}:{value}"

    return app


def _recursive_app() -> App:
    app = App("recursive-app")

    @app.tool(name="count_down")
    def recurse(value: int) -> int:
        return 0 if value == 0 else 1 + recurse(value - 1)

    return app


def _invalid_method_app() -> App:
    app = App("method-app")

    @app.tool()
    def ping() -> str:
        return "pong"

    app._tools[0].info.http_method = "OPENAPI"
    return app


def _ejected(app: App, target: str, module_name: str) -> ModuleType:
    module = ModuleType(module_name)
    source = app.eject(target)
    exec(
        compile(source, f"<{module_name}>", "exec", dont_inherit=True), module.__dict__
    )
    return module


def _mcp_text(result: Any) -> str:
    """Read the semantic text across supported FastMCP result envelopes."""
    content = result if isinstance(result, list) else result.content
    return content[0].text


def test_live_and_ejected_cli_match_behavior() -> None:
    app = _parity_app()
    live = build_typer_app(app.name, app._tools)
    generated = _ejected(app, "cli", "generated_parity_cli").app
    runner = CliRunner()

    help_outputs: list[str] = []
    for cli in (live, generated):
        help_result = runner.invoke(cli, ["--help"])
        default_result = runner.invoke(cli, ["say_hi", "Ada"])
        explicit_result = runner.invoke(cli, ["say_hi", "Ada", "--punctuation", "?"])
        error_result = runner.invoke(cli, ["fail", "--message", "broken"])

        assert help_result.exit_code == 0, help_result.exception
        help_outputs.append(help_result.stdout)
        assert default_result.exit_code == 0, default_result.exception
        assert default_result.stdout == "Hello, Ada!\n"
        assert explicit_result.exit_code == 0, explicit_result.exception
        assert explicit_result.stdout == "Hello, Ada?\n"
        assert error_result.exit_code == 1
        assert isinstance(error_result.exception, ValueError)
        assert str(error_result.exception) == "broken"

    assert help_outputs[0] == help_outputs[1]


def test_live_and_ejected_cli_await_a_returned_coroutine() -> None:
    app = App("dynamic-async")

    @app.tool()
    def deferred(value: str) -> Any:
        return asyncio.sleep(0, result=f"ready:{value}")

    live = build_typer_app(app.name, app._tools)
    generated = _ejected(app, "cli", "generated_dynamic_async_cli").app
    runner = CliRunner()

    for cli in (live, generated):
        result = runner.invoke(cli, ["value"])

        assert result.exit_code == 0, result.exception
        assert result.stdout == "ready:value\n"


def test_live_and_ejected_api_match_behavior_and_contract() -> None:
    from fastapi.testclient import TestClient

    app = _parity_app()
    live: Any = build_fastapi_app(app.name, app._tools)
    generated: Any = _ejected(app, "api", "generated_parity_api").app

    route_names: list[str] = []
    operation_ids: list[str] = []
    for api in (live, generated):
        assert api.title == "parity-app"
        schema = api.openapi()
        operation = schema["paths"]["/say_hi"]["post"]
        route = next(route for route in api.routes if route.path == "/say_hi")
        route_names.append(route.name)
        operation_ids.append(operation["operationId"])
        assert operation.get("parameters", []) == []
        assert "requestBody" in operation
        assert "Person to welcome." in json.dumps(schema)

        client = TestClient(api, raise_server_exceptions=False)
        default_response = client.post("/say_hi", json={"name": "Ada"})
        explicit_response = client.post(
            "/say_hi", json={"name": "Ada", "punctuation": "?"}
        )
        error_response = client.post("/fail", json="broken")

        assert default_response.status_code == 200
        assert default_response.json() == "Hello, Ada!"
        assert explicit_response.status_code == 200
        assert explicit_response.json() == "Hello, Ada?"
        assert error_response.status_code == 500
        assert error_response.text == "Internal Server Error"

    assert route_names == ["say_hi", "say_hi"]
    assert operation_ids[0] == operation_ids[1]


def test_live_and_ejected_api_normalize_unknown_http_methods() -> None:
    from fastapi.testclient import TestClient

    app = _invalid_method_app()
    live: Any = build_fastapi_app(app.name, app._tools)
    generated: Any = _ejected(app, "api", "generated_method_api").app

    for api in (live, generated):
        response = TestClient(api).post("/ping")
        assert response.status_code == 200
        assert response.json() == "pong"


def test_live_and_ejected_api_apply_the_same_untyped_parameter_contract() -> None:
    from fastapi.testclient import TestClient

    app = _untyped_app()
    live: Any = build_fastapi_app(app.name, app._tools)
    generated: Any = _ejected(app, "api", "generated_untyped_api").app

    responses = [
        TestClient(api, raise_server_exceptions=False).post("/classify", json=7)
        for api in (live, generated)
    ]

    assert [response.status_code for response in responses] == [422, 422]


def test_live_and_ejected_mcp_match_behavior() -> None:
    from fastmcp.exceptions import ToolError

    app = _parity_app()
    live: Any = build_fastmcp_app(app.name, app._tools)
    generated: Any = _ejected(app, "mcp", "generated_parity_mcp").mcp

    async def exercise(mcp: Any) -> tuple[Any, Any]:
        default_result = await mcp.call_tool("say_hi", {"name": "Ada"})
        explicit_result = await mcp.call_tool(
            "say_hi", {"name": "Ada", "punctuation": "?"}
        )
        return default_result, explicit_result

    for mcp in (live, generated):
        assert mcp.name == "parity-app"
        default_result, explicit_result = asyncio.run(exercise(mcp))

        assert _mcp_text(default_result) == "Hello, Ada!"
        assert _mcp_text(explicit_result) == "Hello, Ada?"
        try:
            asyncio.run(mcp.call_tool("fail", {"message": "broken"}))
        except ToolError as error:
            assert "broken" in str(error)
        else:
            raise AssertionError("failing MCP tool did not raise ToolError")


def test_live_and_ejected_mcp_apply_the_same_untyped_parameter_contract() -> None:
    app = _untyped_app()
    live: Any = build_fastmcp_app(app.name, app._tools)
    generated: Any = _ejected(app, "mcp", "generated_untyped_mcp").mcp

    async def outcome(mcp: Any) -> tuple[str, str]:
        try:
            result = await mcp.call_tool("classify", {"value": 7})
        except Exception as error:
            return "error", type(error).__name__
        return "ok", _mcp_text(result)

    outcomes = [asyncio.run(outcome(mcp)) for mcp in (live, generated)]

    assert outcomes[0] == outcomes[1]
    assert outcomes[0][0] == "error"


def test_live_and_ejected_interfaces_preserve_renamed_self_references() -> None:
    from fastapi.testclient import TestClient

    app = _recursive_app()
    runner = CliRunner()

    live_cli = build_typer_app(app.name, app._tools)
    generated_cli = _ejected(app, "cli", "generated_recursive_cli").app
    for cli in (live_cli, generated_cli):
        result = runner.invoke(cli, ["3"])
        assert result.exit_code == 0, result.exception
        assert result.stdout == "3\n"

    live_api: Any = build_fastapi_app(app.name, app._tools)
    generated_api: Any = _ejected(app, "api", "generated_recursive_api").app
    for api in (live_api, generated_api):
        response = TestClient(api).post("/count_down", json=3)
        assert response.status_code == 200
        assert response.json() == 3

    live_mcp: Any = build_fastmcp_app(app.name, app._tools)
    generated_mcp: Any = _ejected(app, "mcp", "generated_recursive_mcp").mcp
    for mcp in (live_mcp, generated_mcp):
        result = asyncio.run(mcp.call_tool("count_down", {"value": 3}))
        assert _mcp_text(result) == "3"
