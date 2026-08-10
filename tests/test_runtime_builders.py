"""Tests for runtime framework builders."""

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from intpot.runtime import App, RegisteredTool


def _make_tools() -> tuple[App, list[RegisteredTool]]:
    """Create a test app with two tools and return it with its internal tools."""
    app = App("test-app")

    @app.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @app.tool()
    def greet(name: str, greeting: str = "Hello") -> str:
        """Greet someone."""
        return f"{greeting}, {name}!"

    return app, app._tools


def test_build_typer_app():
    from typer.main import get_group

    from intpot.runtime_builders import build_typer_app

    _, tools = _make_tools()
    cli_app = build_typer_app("test", tools)

    # Verify commands are registered via Click group
    group = get_group(cli_app)
    command_names = list(group.commands.keys())
    assert "add" in command_names
    assert "greet" in command_names


def test_build_fastapi_app():
    from intpot.runtime_builders import build_fastapi_app

    _, tools = _make_tools()
    api_app = build_fastapi_app("test", tools)

    # Verify routes are registered
    route_paths = [r.path for r in api_app.routes if hasattr(r, "methods")]
    assert "/add" in route_paths
    assert "/greet" in route_paths


def test_build_fastmcp_app():
    from intpot.runtime_builders import build_fastmcp_app

    _, tools = _make_tools()
    mcp_app = build_fastmcp_app("test", tools)

    # FastMCP stores tools internally — check the name
    assert mcp_app.name == "test"


def _openapi_operation(api_app, path: str, method: str = "post") -> dict:
    return api_app.openapi()["paths"][path][method]


def test_fastapi_params_come_from_the_body_not_the_query_string():
    """Generated code declares Body(...), so the live server must agree.

    Registering the plain function let FastAPI infer a location per parameter,
    and scalars became query parameters — so `serve --api` and `eject --to api`
    exposed two different HTTP interfaces for the same app.
    """
    from intpot.runtime_builders import build_fastapi_app

    _, tools = _make_tools()
    api_app = build_fastapi_app("test", tools)

    operation = _openapi_operation(api_app, "/add")

    assert "requestBody" in operation
    assert operation.get("parameters", []) == []


def test_fastapi_endpoint_serves_a_real_request():
    from fastapi.testclient import TestClient

    from intpot.runtime_builders import build_fastapi_app

    _, tools = _make_tools()
    api_app: Any = build_fastapi_app("test", tools)
    client = TestClient(api_app)

    response = client.post("/add", json={"a": 2, "b": 3})

    assert response.status_code == 200
    assert response.json() == 5


def test_fastapi_endpoint_awaits_async_tools():
    from fastapi.testclient import TestClient

    from intpot.runtime_builders import build_fastapi_app

    app = App("async-app")

    @app.tool()
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

    api_app: Any = build_fastapi_app("test", app._tools)
    client = TestClient(api_app)

    # A lone Body() parameter is not embedded by FastAPI, so the body is the
    # value itself — the generated code behaves the same way.
    response = client.post("/greet", json="World")

    assert response.status_code == 200
    assert response.json() == "Hello, World!"


def test_serving_and_ejecting_expose_the_same_interface():
    """The invariant behind this whole builder: one app, one HTTP surface.

    `serve --api` and `eject --to api` must not disagree about where a
    parameter comes from.
    """
    from intpot.core.generators.api import APIGenerator
    from intpot.runtime_builders import build_fastapi_app

    app, tools = _make_tools()

    live = build_fastapi_app("test", tools)
    namespace: dict[str, Any] = {}
    exec(compile(APIGenerator().generate(app.tools), "<generated>", "exec"), namespace)
    generated = namespace["app"]

    def interface(api_app) -> list[tuple]:
        paths = api_app.openapi()["paths"]
        return sorted(
            (
                path,
                method,
                tuple(sorted((p["name"], p["in"]) for p in op.get("parameters", []))),
                "requestBody" in op,
            )
            for path, methods in paths.items()
            for method, op in methods.items()
        )

    assert interface(live) == interface(generated)


def test_fastapi_honours_a_declared_param_source():
    """A tool carrying param_source=query keeps its query parameter."""
    from intpot.core.models import ParameterInfo, ParamSource, ToolInfo
    from intpot.runtime_builders import build_fastapi_app

    def search(term: str) -> str:
        return f"searching {term}"

    tool = RegisteredTool(
        func=search,
        info=ToolInfo(
            name="search",
            parameters=[
                ParameterInfo(
                    name="term",
                    type_annotation="str",
                    param_source=ParamSource.query,
                )
            ],
        ),
    )

    operation = _openapi_operation(build_fastapi_app("test", [tool]), "/search")

    assert [(p["name"], p["in"]) for p in operation["parameters"]] == [
        ("term", "query")
    ]
    assert "requestBody" not in operation


def test_fastapi_falls_back_to_post_for_an_unknown_method():
    from intpot.core.models import ToolInfo
    from intpot.runtime_builders import build_fastapi_app

    def ping() -> str:
        return "pong"

    tool = RegisteredTool(func=ping, info=ToolInfo(name="ping", http_method="openapi"))

    api_app = build_fastapi_app("test", [tool])

    assert list(api_app.openapi()["paths"]["/ping"]) == ["post"]


def test_build_typer_app_runs_async_tool():
    from intpot.runtime_builders import build_typer_app

    app = App("async-app")

    @app.tool()
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

    cli_app = build_typer_app("test", app._tools)

    result = CliRunner().invoke(cli_app, ["World"])

    assert result.exit_code == 0
    assert "Hello, World!" in result.output
