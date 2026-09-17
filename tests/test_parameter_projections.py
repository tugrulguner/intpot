"""Target parameter projection and live/generated boundary tests."""

from __future__ import annotations

import asyncio
from types import ModuleType
from typing import Any

import pytest
from typer.testing import CliRunner

from intpot import App
from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import (
    _SENTINEL,
    ApplicationSchema,
    ParameterInfo,
    ParameterPlacement,
    ParameterSchema,
    ParamSource,
    SourceType,
    ToolInfo,
    ToolSchema,
)
from intpot.core.projections import (
    project_parameter_placement,
    resolve_parameter_placement,
)
from intpot.runtime import RegisteredTool
from intpot.runtime_builders import (
    build_fastapi_app,
    build_fastmcp_app,
    build_typer_app,
)


@pytest.mark.parametrize(
    ("target", "required", "source", "expected"),
    [
        (SourceType.CLI, True, ParamSource.header, ParameterPlacement.CLI_ARGUMENT),
        (SourceType.CLI, False, ParamSource.path, ParameterPlacement.CLI_OPTION),
        (SourceType.API, True, None, ParameterPlacement.API_BODY),
        (SourceType.API, True, ParamSource.query, ParameterPlacement.API_QUERY),
        (SourceType.API, True, ParamSource.header, ParameterPlacement.API_HEADER),
        (SourceType.API, True, ParamSource.path, ParameterPlacement.API_PATH),
        (SourceType.MCP, True, ParamSource.query, ParameterPlacement.MCP_PARAMETER),
        (SourceType.MCP, False, None, ParameterPlacement.MCP_PARAMETER),
    ],
)
def test_parameter_placement_matrix(target, required, source, expected) -> None:
    parameter = ParameterSchema(
        "value",
        default=(... if not required else _SENTINEL),
        param_source=source,
    )

    assert resolve_parameter_placement(parameter, target) is expected


def test_projection_is_immutable_and_structurally_shares_unchanged_records() -> None:
    already_projected = ParameterSchema(
        "ready", placement=ParameterPlacement.MCP_PARAMETER
    )
    unresolved = ParameterSchema("other", default="value")
    shared_tool = ToolSchema(name="shared", parameters=(already_projected,))
    changed_tool = ToolSchema(name="changed", parameters=(unresolved,))
    source = ApplicationSchema(
        name="projection",
        source_type=SourceType.PYTHON,
        tools=(shared_tool, changed_tool),
    )

    projected = project_parameter_placement(source, SourceType.MCP)

    assert source.target_type is None
    assert source.tools == (shared_tool, changed_tool)
    assert source.tools[1].parameters[0].placement is None
    assert projected is not source
    assert projected.target_type is SourceType.MCP
    assert projected.tools[0] is shared_tool
    assert projected.tools[0].parameters[0] is already_projected
    assert projected.tools[1] is not changed_tool
    assert projected.tools[1].parameters[0] is not unresolved
    assert (
        projected.tools[1].parameters[0].placement is ParameterPlacement.MCP_PARAMETER
    )


def test_compatibility_mapping_preserves_explicit_placement() -> None:
    info = ParameterInfo(
        "term",
        description="Search phrase.",
        param_source=ParamSource.query,
        placement=ParameterPlacement.API_QUERY,
    )

    schema = ParameterSchema.from_info(info)
    detached = schema.to_info()

    assert schema.placement is ParameterPlacement.API_QUERY
    assert detached.placement is ParameterPlacement.API_QUERY
    assert schema.to_dict()["placement"] == "api_query"


@pytest.mark.parametrize(
    ("generator", "target", "expected"),
    [
        (CLIGenerator(), SourceType.CLI, ParameterPlacement.CLI_ARGUMENT),
        (APIGenerator(), SourceType.API, ParameterPlacement.API_QUERY),
        (MCPGenerator(), SourceType.MCP, ParameterPlacement.MCP_PARAMETER),
    ],
)
def test_generators_normalize_unprojected_schema_to_their_target(
    monkeypatch, generator, target, expected
) -> None:
    schema = ApplicationSchema(
        name="normalization",
        source_type=SourceType.PYTHON,
        tools=(
            ToolSchema(
                name="show",
                parameters=(ParameterSchema("term", param_source=ParamSource.query),),
            ),
        ),
    )
    observed: list[ApplicationSchema] = []

    def capture(template_name: str, **kwargs: object) -> str:
        observed.append(kwargs["schema"])  # type: ignore[arg-type]
        return template_name

    module = __import__(generator.__class__.__module__, fromlist=["render_template"])
    monkeypatch.setattr(module, "render_template", capture)

    generator.generate(schema)

    assert observed[0].target_type is target
    assert observed[0].tools[0].parameters[0].placement is expected


def _placement_app() -> App:
    app = App("placements")

    @app.tool(description="Look up an item.")
    def lookup(
        item_id: int,
        payload: str,
        query: str = "all",
        token: str = "public",
    ) -> str:
        return f"{item_id}:{payload}:{query}:{token}"

    tool = app._tools[0].info
    tool.route_path = "/items/{item_id}"
    tool.parameters[0].param_source = ParamSource.path
    tool.parameters[0].description = "Item identifier."
    tool.parameters[1].param_source = ParamSource.body
    tool.parameters[1].description = "Request payload."
    tool.parameters[2].param_source = ParamSource.query
    tool.parameters[2].description = "Result filter."
    tool.parameters[3].param_source = ParamSource.header
    tool.parameters[3].description = "Access token."
    return app


def _ejected(app: App, target: str) -> ModuleType:
    module = ModuleType(f"generated_{target}_placement")
    exec(compile(app.eject(target), f"<generated-{target}>", "exec"), module.__dict__)
    return module


def test_live_and_ejected_cli_use_projected_argument_option_descriptions() -> None:
    app = _placement_app()
    live = build_typer_app(app.name, app._tools)
    generated = _ejected(app, "cli").app

    for cli in (live, generated):
        help_result = CliRunner().invoke(cli, ["--help"])
        call_result = CliRunner().invoke(
            cli,
            ["7", "hello", "--query", "open", "--token", "secret"],
        )

        assert help_result.exit_code == 0, help_result.exception
        assert "Item identifier." in help_result.stdout
        assert "Request payload." in help_result.stdout
        assert "Result filter." in help_result.stdout
        assert "Access token." in help_result.stdout
        assert call_result.exit_code == 0, call_result.exception
        assert call_result.stdout == "7:hello:open:secret\n"


def test_live_and_ejected_api_use_body_query_header_and_path_placements() -> None:
    from fastapi.testclient import TestClient

    app = _placement_app()
    live: Any = build_fastapi_app(app.name, app._tools)
    generated: Any = _ejected(app, "api").app

    for api in (live, generated):
        operation = api.openapi()["paths"]["/items/{item_id}"]["post"]
        locations = {
            (parameter["name"], parameter["in"])
            for parameter in operation["parameters"]
        }
        assert locations == {
            ("item_id", "path"),
            ("query", "query"),
            ("token", "header"),
        }
        assert "requestBody" in operation
        rendered_schema = str(operation)
        for description in (
            "Item identifier.",
            "Request payload.",
            "Result filter.",
            "Access token.",
        ):
            assert description in rendered_schema

        response = TestClient(api).post(
            "/items/7?query=open",
            headers={"token": "secret"},
            json="hello",
        )
        assert response.status_code == 200, response.text
        assert response.json() == "7:hello:open:secret"


def test_live_and_ejected_mcp_preserve_required_and_default_parameters() -> None:
    app = _placement_app()
    live: Any = build_fastmcp_app(app.name, app._tools)
    generated: Any = _ejected(app, "mcp").mcp

    async def call(mcp: Any) -> Any:
        return await mcp.call_tool("lookup", {"item_id": 7, "payload": "hello"})

    for mcp in (live, generated):
        result = asyncio.run(call(mcp))
        content = result if isinstance(result, list) else result.content
        assert content[0].text == "7:hello:all:public"


def test_live_builders_resolve_opaque_defaults_without_application_schema() -> None:
    class Opaque:
        pass

    opaque = Opaque()

    def identify(value: object = opaque) -> bool:
        return value is opaque

    registered = RegisteredTool(
        func=identify,
        info=ToolInfo(
            name="identify",
            parameters=[
                ParameterInfo("value", type_annotation="object", default=opaque)
            ],
            return_type="bool",
        ),
    )

    assert (
        resolve_parameter_placement(registered.info.parameters[0], SourceType.MCP)
        is ParameterPlacement.MCP_PARAMETER
    )
    mcp: Any = build_fastmcp_app("opaque", [registered])
    result = asyncio.run(mcp.call_tool("identify", {}))
    content = result if isinstance(result, list) else result.content
    assert content[0].text == "true"
