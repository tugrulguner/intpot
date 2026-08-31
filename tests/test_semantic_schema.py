"""Tests for Intpot's canonical application schema."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import ModuleType

import pytest

import intpot
from intpot.core.generators.api import APIGenerator
from intpot.core.generators.cli import CLIGenerator
from intpot.core.generators.mcp import MCPGenerator
from intpot.core.models import ApplicationSchema, SourceType


def test_load_compiles_an_immutable_application_schema(tmp_source) -> None:
    source = tmp_source(
        """
        from fastmcp import FastMCP

        mcp = FastMCP("weather-tools")

        @mcp.tool()
        def forecast(city: str, days: int = 1) -> str:
            \"\"\"Return a forecast.\"\"\"
            return f"{city}: {days} day(s)"
        """
    )

    loaded = intpot.load(source)
    schema = loaded.schema

    assert isinstance(schema, ApplicationSchema)
    assert schema.name == "weather-tools"
    assert schema.source_type is SourceType.MCP
    assert schema.source_path == source.resolve()
    assert isinstance(schema.tools, tuple)
    assert schema.tools[0].name == "forecast"
    assert isinstance(schema.tools[0].parameters, tuple)
    assert schema.tools[0].parameters[0].name == "city"
    assert schema.tools[0].parameters[0].required

    with pytest.raises(FrozenInstanceError):
        schema.name = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        schema.tools[0].name = "changed"  # type: ignore[misc]


def test_public_projection_uses_the_schema_without_mutating_it(tmp_source) -> None:
    source = tmp_source(
        """
        from fastmcp import FastMCP

        mcp = FastMCP("calculator")

        @mcp.tool()
        def add(a: int, b: int) -> int:
            return a + b
        """
    )
    loaded = intpot.load(source)
    original = loaded.schema

    detached_tools = loaded.tools
    detached_tools[0].name = "mutated"
    projected = loaded.project("api")

    assert intpot.ApplicationSchema is ApplicationSchema
    assert intpot.SourceType is SourceType
    assert original.target_type is None
    assert original.tools[0].name == "add"
    assert projected.source_type is SourceType.MCP
    assert projected.target_type is SourceType.API
    assert projected.tools[0].name == "add"
    assert projected.tools[0].return_type == "dict"
    assert projected.tools[0].function_body == "return {'result': a + b}"

    generated = loaded.to_api()
    assert "def add(" in generated
    assert "mutated" not in generated

    with pytest.raises(ValueError, match="expected: cli, mcp, api"):
        loaded.project("python")


def test_runtime_app_meets_conversion_at_the_same_schema() -> None:
    app = intpot.App("inventory")

    @app.tool()
    def lookup(sku: str) -> str:
        return sku.upper()

    schema = app.schema
    detached_tools = app.tools
    detached_tools[0].name = "mutated"

    assert schema.name == "inventory"
    assert schema.source_type is SourceType.PYTHON
    assert schema.tools[0].name == "lookup"
    assert app.schema is schema
    assert "def lookup(" in app.eject("mcp")
    assert "mutated" not in app.eject("mcp")


def test_schema_serializes_required_parameters_without_leaking_the_sentinel(
    tmp_source,
) -> None:
    source = tmp_source(
        """
        import typer

        app = typer.Typer(name="greeter")

        @app.command()
        def greet(name: str, loud: bool = False) -> None:
            typer.echo(name.upper() if loud else name)
        """
    )

    data = intpot.load(source).schema.to_dict()

    assert data["name"] == "greeter"
    assert data["source_type"] == "cli"
    assert data["source_path"] == str(source.resolve())
    assert data["target_type"] is None
    assert data["tools"][0]["parameters"][0] == {
        "name": "name",
        "type_annotation": "str",
        "description": "",
        "param_source": None,
        "required": True,
    }
    assert data["tools"][0]["parameters"][1]["default"] is False


@pytest.mark.parametrize(
    ("generator", "global_name", "attribute"),
    [
        (CLIGenerator(), "app", "info"),
        (APIGenerator(), "app", "title"),
        (MCPGenerator(), "mcp", "name"),
    ],
)
def test_generators_consume_application_schema_and_preserve_its_name(
    generator,
    global_name: str,
    attribute: str,
) -> None:
    app = intpot.App("inventory")

    @app.tool()
    def lookup(sku: str) -> str:
        return sku.upper()

    code = generator.generate(app.schema)
    generated = ModuleType("generated")
    exec(compile(code, "generated.py", "exec"), generated.__dict__)
    framework_app = getattr(generated, global_name)

    if attribute == "info":
        assert framework_app.info.name == "inventory"
    else:
        assert getattr(framework_app, attribute) == "inventory"


def test_schema_detaches_and_freezes_mutable_parameter_defaults() -> None:
    original_default = [{"region": "us"}]
    app = intpot.App("defaults")

    @app.tool()
    def configure(regions: list[dict[str, str]] = original_default) -> int:
        return len(regions)

    schema_default = app.schema.tools[0].parameters[0].default
    original_default[0]["region"] = "eu"

    assert isinstance(schema_default, tuple)
    assert [dict(item) for item in schema_default] == [{"region": "us"}]
    with pytest.raises(TypeError):
        schema_default[0]["region"] = "eu"

    first_compatibility_default = app.tools[0].parameters[0].default
    first_compatibility_default[0]["region"] = "apac"
    second_compatibility_default = app.tools[0].parameters[0].default

    assert second_compatibility_default == [{"region": "us"}]
    assert app.schema.to_dict()["tools"][0]["parameters"][0]["default"] == [
        {"region": "us"}
    ]


def test_public_schema_constructors_freeze_nested_collections() -> None:
    from intpot import ApplicationSchema, ParameterSchema, SourceType, ToolSchema

    default = [{"region": "us"}]
    parameters = [ParameterSchema(name="filters", default=default)]
    dependencies = ["auth"]
    tools = [
        ToolSchema(
            name="search",
            parameters=parameters,  # type: ignore[arg-type]
            dependencies=dependencies,  # type: ignore[arg-type]
        )
    ]

    schema = ApplicationSchema(
        name="catalog",
        source_type=SourceType.PYTHON,
        tools=tools,  # type: ignore[arg-type]
    )
    default[0]["region"] = "eu"
    parameters.clear()
    dependencies.clear()
    tools.clear()

    assert len(schema.tools) == 1
    assert len(schema.tools[0].parameters) == 1
    assert schema.tools[0].dependencies == ("auth",)
    frozen_default = schema.tools[0].parameters[0].default
    assert [dict(item) for item in frozen_default] == [{"region": "us"}]
    with pytest.raises(TypeError):
        frozen_default[0]["region"] = "apac"


def test_application_names_follow_framework_semantics_and_path_fallback(
    tmp_source,
) -> None:
    default_api = tmp_source(
        """
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/health")
        def health() -> dict:
            return {"ok": True}
        """,
        name="service.py",
    )
    titled_api = tmp_source(
        """
        from fastapi import FastAPI

        app = FastAPI(title="Orders")

        @app.get("/health")
        def health() -> dict:
            return {"ok": True}
        """,
        name="orders.py",
    )

    assert intpot.load(default_api).schema.name == "service"
    assert intpot.load(titled_api).schema.name == "Orders"
