"""Target-visible tool naming across live and generated interfaces."""

from __future__ import annotations

import asyncio
from types import ModuleType
from typing import Any

from typer.testing import CliRunner

import intpot
from intpot import App
from intpot.core.models import ApplicationSchema, SourceType, ToolInfo, ToolSchema
from intpot.runtime_builders import (
    build_fastapi_app,
    build_fastmcp_app,
    build_typer_app,
)


def _named_app() -> App:
    app = App("naming")

    @app.tool(name="send-email")
    def send_email(address: str) -> str:
        return f"sent:{address}"

    @app.tool()
    def status() -> str:
        return "ready"

    return app


def _ejected(app: App, target: str) -> ModuleType:
    module = ModuleType(f"generated_{target}_naming")
    exec(compile(app.eject(target), f"<generated-{target}>", "exec"), module.__dict__)
    return module


def test_live_and_ejected_interfaces_preserve_explicit_tool_names() -> None:
    from fastapi.testclient import TestClient

    app = _named_app()
    live_cli = build_typer_app(app.name, app._tools)
    generated_cli = _ejected(app, "cli").app
    live_api: Any = build_fastapi_app(app.name, app._tools)
    generated_api: Any = _ejected(app, "api").app
    live_mcp: Any = build_fastmcp_app(app.name, app._tools)
    generated_mcp: Any = _ejected(app, "mcp").mcp

    for cli in (live_cli, generated_cli):
        result = CliRunner().invoke(cli, ["send-email", "ada@example.com"])
        assert result.exit_code == 0, result.exception
        assert result.stdout == "sent:ada@example.com\n"

    for api in (live_api, generated_api):
        route = next(route for route in api.routes if route.path == "/send-email")
        response = TestClient(api).post("/send-email", json="ada@example.com")
        assert route.name == "send-email"
        assert response.status_code == 200, response.text
        assert response.json() == "sent:ada@example.com"

    async def call(mcp: Any) -> str:
        result = await mcp.call_tool("send-email", {"address": "ada@example.com"})
        content = result if isinstance(result, list) else result.content
        return content[0].text

    for mcp in (live_mcp, generated_mcp):
        assert asyncio.run(call(mcp)) == "sent:ada@example.com"


def test_target_name_projection_makes_default_api_paths_explicit() -> None:
    from intpot.core.projections import project_tool_names

    tool = ToolSchema(name="send-email")
    source = ApplicationSchema(
        name="naming", source_type=SourceType.PYTHON, tools=(tool,)
    )

    api = project_tool_names(source, SourceType.API)
    cli = project_tool_names(source, SourceType.CLI)

    assert tool.name == "send_email"
    assert tool.interface_name == "send-email"
    assert tool.route_path is None
    assert api.target_type is SourceType.API
    assert api.tools[0].interface_name == "send-email"
    assert api.tools[0].route_path == "/send-email"
    assert project_tool_names(api, SourceType.API) is api
    assert cli.tools[0] is tool


def test_mutable_compatibility_names_still_follow_renames() -> None:
    from intpot.core.projections import resolve_tool_interface_name

    tool = ToolInfo(name="before")

    tool.name = "after"

    assert resolve_tool_interface_name(tool, SourceType.MCP) == "after"


def test_quoted_tool_names_generate_valid_api_routes() -> None:
    app = App("quoted")

    @app.tool(name='say"hi')
    def say_hi() -> str:
        return "ok"

    source = app.eject("api")
    module = ModuleType("generated_quoted_api")
    exec(compile(source, "<generated-quoted-api>", "exec"), module.__dict__)

    route = next(route for route in module.app.routes if route.name == 'say"hi')
    assert route.path == '/say"hi'


def test_inspected_mcp_names_survive_generated_runtime() -> None:
    from fastmcp import FastMCP

    from intpot.core.generators.mcp import MCPGenerator
    from intpot.core.inspectors.mcp import MCPInspector

    source = FastMCP("source")

    @source.tool(name="send-email")
    def send_email(address: str) -> str:
        return f"sent:{address}"

    tools = MCPInspector().inspect(source)
    generated: Any = _ejected_source(
        MCPGenerator().generate(tools), "inspected_mcp"
    ).mcp

    assert tools[0].name == "send_email"
    assert tools[0].interface_name == "send-email"

    async def call() -> str:
        result = await generated.call_tool("send-email", {"address": "ada@example.com"})
        content = result if isinstance(result, list) else result.content
        return content[0].text

    assert asyncio.run(call()) == "sent:ada@example.com"


def _ejected_source(source: str, module_name: str) -> ModuleType:
    module = ModuleType(module_name)
    exec(compile(source, f"<{module_name}>", "exec"), module.__dict__)
    return module


def test_typer_default_command_name_survives_conversion() -> None:
    import typer

    source = typer.Typer()

    @source.command()
    def hello_world() -> None:
        typer.echo("hello")

    generated: Any = _ejected_source(
        intpot.load(source).to_mcp(), "typer_name_to_mcp"
    ).mcp

    async def call() -> str:
        result = await generated.call_tool("hello-world", {})
        content = result if isinstance(result, list) else result.content
        return content[0].text

    assert asyncio.run(call()) == "hello"


def test_fastapi_route_name_survives_conversion() -> None:
    from fastapi import FastAPI

    source = FastAPI()

    @source.get("/health", name="public-health", operation_id="healthCheck")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    generated: Any = _ejected_source(
        intpot.load(source).to_mcp(), "api_name_to_mcp"
    ).mcp

    async def call() -> str:
        result = await generated.call_tool("public-health", {})
        content = result if isinstance(result, list) else result.content
        return content[0].text

    assert asyncio.run(call()) == '{"status":"ok"}'
