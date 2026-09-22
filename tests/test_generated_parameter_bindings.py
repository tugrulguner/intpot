"""Executable regressions for generated parameter bindings."""

from __future__ import annotations

import asyncio
import inspect
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from intpot import App
from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import ParameterInfo, ParameterSchema, ToolInfo, ToolSchema


def _app() -> App:
    app = App("parameter-bindings")

    @app.tool()
    def combine(user__id: str = "left", user_id: str = "right") -> str:
        return f"{user__id}:{user_id}"

    @app.tool()
    def status() -> str:
        return "ready"

    return app


def _ejected(app: App, target: str) -> ModuleType:
    module = ModuleType(f"generated_{target}_parameter_bindings")
    exec(
        compile(app.eject(target), f"<generated-{target}>", "exec"),
        module.__dict__,
    )
    return module


def test_canonical_schema_preserves_callable_parameter_bindings() -> None:
    info = ToolInfo(
        name="combine",
        parameters=[ParameterInfo("user__id"), ParameterInfo("user_id")],
    )

    schema = ToolSchema.from_info(info)

    assert [parameter.name for parameter in schema.parameters] == [
        "user_id",
        "user_id_2",
    ]
    assert [parameter.binding_name for parameter in schema.parameters] == [
        "user__id",
        "user_id",
    ]
    assert schema.to_dict()["parameters"][0]["binding_name"] == "user__id"
    assert [parameter.binding_name for parameter in schema.to_info().parameters] == [
        "user__id",
        "user_id",
    ]


def test_generated_cli_preserves_callable_parameter_bindings() -> None:
    generated = _ejected(_app(), "cli")

    result = CliRunner().invoke(
        generated.app,
        ["combine", "--user-id", "alice", "--user-id-2", "bob"],
    )

    assert result.exit_code == 0, result.exception
    assert result.stdout == "alice:bob\n"
    assert list(inspect.signature(generated.combine).parameters) == [
        "user_id",
        "user_id_2",
    ]


def test_generated_api_preserves_callable_parameter_bindings() -> None:
    generated = _ejected(_app(), "api")

    response = TestClient(generated.app, raise_server_exceptions=False).post(
        "/combine", json={"user_id": "alice", "user_id_2": "bob"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == "alice:bob"
    assert list(inspect.signature(generated.combine).parameters) == [
        "user_id",
        "user_id_2",
    ]


def test_generated_mcp_preserves_callable_parameter_bindings() -> None:
    generated: Any = _ejected(_app(), "mcp")

    async def call() -> str:
        result = await generated.mcp.call_tool(
            "combine", {"user_id": "alice", "user_id_2": "bob"}
        )
        content = result if isinstance(result, list) else result.content
        return content[0].text

    assert asyncio.run(call()) == "alice:bob"
    assert list(inspect.signature(generated.combine).parameters) == [
        "user_id",
        "user_id_2",
    ]


@pytest.mark.parametrize("binding_name", ["class", "x-y", ""])
def test_parameter_bindings_must_be_valid_python_names(binding_name: str) -> None:
    with pytest.raises(ValueError, match="Invalid Python parameter binding name"):
        ParameterInfo("value", binding_name=binding_name)
    with pytest.raises(ValueError, match="Invalid Python parameter binding name"):
        ParameterSchema("value", binding_name=binding_name)


@pytest.mark.parametrize("generator", [CLIGenerator, APIGenerator, MCPGenerator])
def test_private_bindings_cannot_collide_with_later_canonical_names(generator) -> None:
    tool = ToolInfo(
        "collision",
        parameters=[
            ParameterInfo("x__2"),
            ParameterInfo("x-"),
            ParameterInfo("x_"),
        ],
        function_body="return x__2",
    )

    source = generator().generate([tool])
    compile(source, "<generated>", "exec")
    assert [
        parameter.binding_name or parameter.name for parameter in tool.parameters
    ] == [
        "x__2",
        "x__3",
        "x_",
    ]


@pytest.mark.parametrize("generator", [CLIGenerator, APIGenerator, MCPGenerator])
def test_explicit_binding_collisions_are_allocated_safely(generator) -> None:
    tool = ToolInfo(
        "collision",
        parameters=[
            ParameterInfo("x", binding_name="y"),
            ParameterInfo("y"),
        ],
        function_body="return y",
    )

    source = generator().generate([tool])
    compile(source, "<generated>", "exec")
    assert [
        parameter.binding_name or parameter.name for parameter in tool.parameters
    ] == [
        "y",
        "y_2",
    ]


def test_direct_tool_schema_allocates_noncolliding_private_bindings() -> None:
    schema = ToolSchema(
        "collision",
        parameters=(
            ParameterSchema("x", binding_name="y"),
            ParameterSchema("y"),
        ),
    )

    assert [parameter.name for parameter in schema.parameters] == ["x", "y"]
    assert [
        parameter.binding_name or parameter.name for parameter in schema.parameters
    ] == [
        "y",
        "y_2",
    ]


def test_async_generated_bindings_execute_in_every_target() -> None:
    app = App("async-parameter-bindings")

    @app.tool()
    async def combine_async(user__id: str = "left", user_id: str = "right") -> str:
        await asyncio.sleep(0)
        return f"{user__id}:{user_id}"

    cli = _ejected(app, "cli")
    cli_result = CliRunner().invoke(
        cli.app,
        ["--user-id", "alice", "--user-id-2", "bob"],
    )
    assert cli_result.exit_code == 0, cli_result.exception
    assert cli_result.stdout == "alice:bob\n"

    api = _ejected(app, "api")
    api_response = TestClient(api.app).post(
        "/combine_async", json={"user_id": "alice", "user_id_2": "bob"}
    )
    assert api_response.status_code == 200
    assert api_response.json() == "alice:bob"

    mcp: Any = _ejected(app, "mcp")

    async def call_mcp() -> str:
        result = await mcp.mcp.call_tool(
            "combine_async", {"user_id": "alice", "user_id_2": "bob"}
        )
        content = result if isinstance(result, list) else result.content
        return content[0].text

    assert asyncio.run(call_mcp()) == "alice:bob"


def test_recursive_generated_bindings_execute_in_every_target() -> None:
    app = App("recursive-parameter-bindings")

    @app.tool()
    def countdown(user__remaining: int = 2, user_remaining: int = 10) -> int:
        if user__remaining <= 0:
            return user_remaining
        return countdown(
            user__remaining=user__remaining - 1,
            user_remaining=user_remaining + 1,
        )

    @app.tool()
    def status() -> str:
        return "ready"

    cli = _ejected(app, "cli")
    cli_result = CliRunner().invoke(
        cli.app,
        ["countdown", "--user-remaining", "2", "--user-remaining-2", "10"],
    )
    assert cli_result.exit_code == 0, cli_result.exception
    assert cli_result.stdout == "12\n"

    api = _ejected(app, "api")
    api_response = TestClient(api.app).post(
        "/countdown", json={"user_remaining": 2, "user_remaining_2": 10}
    )
    assert api_response.status_code == 200
    assert api_response.json() == 12

    mcp: Any = _ejected(app, "mcp")

    async def call_mcp() -> str:
        result = await mcp.mcp.call_tool(
            "countdown", {"user_remaining": 2, "user_remaining_2": 10}
        )
        content = result if isinstance(result, list) else result.content
        return content[0].text

    assert asyncio.run(call_mcp()) == "12"


@pytest.mark.parametrize("generator", [APIGenerator, MCPGenerator])
def test_private_implementation_names_reject_retained_import_collisions(
    generator,
) -> None:
    tool = ToolInfo(
        "square_root",
        parameters=[ParameterInfo("value", type_annotation="float")],
        return_type="float",
        function_body="return _square_root_impl(value)",
        source_imports=["from math import sqrt as _square_root_impl"],
    )

    with pytest.raises(ValueError, match="collide with generated names"):
        generator().generate([tool])
