from __future__ import annotations

import json
from enum import Enum
from types import ModuleType
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from intpot.core.generators.api import APIGenerator
from intpot.core.inspectors.api import APIInspector
from intpot.core.models import ApplicationSchema, SourceType, ToolInfo, ToolSchema
from intpot.runtime import RegisteredTool
from intpot.runtime_builders import build_fastapi_app


def _route(app: Any, path: str) -> Any:
    return next(route for route in app.routes if getattr(route, "path", None) == path)


def test_new_metadata_does_not_shift_existing_positional_tool_fields() -> None:
    info = ToolInfo(
        "health",
        "Health check.",
        [],
        "dict",
        "GET",
        "return {'status': 'ok'}",
        False,
        "/health",
        ["Depends(auth)"],
        ["from app import auth"],
        "public-health",
    )
    schema = ToolSchema(
        "health",
        "Health check.",
        (),
        "dict",
        "GET",
        "return {'status': 'ok'}",
        False,
        "/health",
        ("Depends(auth)",),
        ("from app import auth",),
        "public-health",
    )

    assert info.dependencies == ["Depends(auth)"]
    assert schema.dependencies == ("Depends(auth)",)
    assert info.source_imports == ["from app import auth"]
    assert schema.source_imports == ("from app import auth",)
    assert info.interface_name == schema.interface_name == "public-health"
    assert info.operation_id is schema.operation_id is None
    assert info.route_tags == []
    assert schema.route_tags == ()


def test_fastapi_inspector_preserves_effective_route_metadata() -> None:
    source = FastAPI()

    class Audience(str, Enum):
        public = "public"

    @source.get(
        "/health",
        name="public-health",
        operation_id="healthCheck",
        summary="Service health",
        description="Reports whether the service is ready.",
        tags=["operations", Audience.public],
        deprecated=True,
    )
    def health() -> dict[str, str]:
        """Internal handler documentation."""
        return {"status": "ok"}

    tool = APIInspector().inspect(source)[0]

    assert tool.interface_name == "public-health"
    assert tool.operation_id == "healthCheck"
    assert tool.route_summary == "Service health"
    assert tool.route_description == "Reports whether the service is ready."
    assert tool.route_tags == ["operations", "public"]
    assert tool.route_deprecated is True

    schema = ApplicationSchema.from_tools(
        name="metadata", source_type=SourceType.API, tools=(tool,)
    )
    frozen = schema.tools[0]
    assert frozen.operation_id == "healthCheck"
    assert frozen.route_summary == "Service health"
    assert frozen.route_description == "Reports whether the service is ready."
    assert frozen.route_tags == ("operations", "public")
    assert frozen.route_deprecated is True
    mutable = frozen.to_info()
    assert mutable.route_tags == ["operations", "public"]
    mutable.route_tags.append("mutated")
    assert frozen.route_tags == ("operations", "public")
    assert frozen.to_dict()["route_tags"] == ["operations", "public"]
    json.dumps(schema.to_dict())
    compile(APIGenerator().generate(schema), "<generated>", "exec")


def test_inferred_fastapi_summary_survives_inspection_live_and_generation() -> None:
    source = FastAPI()

    @source.get("/health", name="public-health")
    def health() -> dict[str, str]:
        """Report service health.

        This detail belongs in the operation description, not its summary.
        """
        return {"status": "ok"}

    expected_operation = source.openapi()["paths"]["/health"]["get"]
    assert expected_operation["summary"] == "Public-Health"

    [info] = APIInspector().inspect(source)
    assert info.route_summary == "Public-Health"

    live: Any = build_fastapi_app("metadata", [RegisteredTool(func=health, info=info)])
    schema = ApplicationSchema.from_tools(
        name="metadata", source_type=SourceType.API, tools=(info,)
    )
    generated = ModuleType("generated_inferred_summary")
    exec(
        compile(APIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (live, generated.app):
        operation = app.openapi()["paths"]["/health"]["get"]
        assert operation["summary"] == expected_operation["summary"]
        assert operation["description"] == expected_operation["description"]
        assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_empty_fastapi_route_name_and_its_inferred_summary_are_preserved() -> None:
    source = FastAPI()

    @source.get("/health", name="")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    [info] = APIInspector().inspect(source)
    assert info.interface_name == ""
    assert info.route_summary == ""

    schema = ApplicationSchema.from_tools(
        name="metadata", source_type=SourceType.API, tools=(info,)
    )
    generated = ModuleType("generated_empty_route_name")
    exec(
        compile(APIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    source_route = _route(source, "/health")
    generated_route = _route(generated.app, "/health")
    assert generated_route.name == source_route.name == ""
    assert generated.app.openapi()["paths"]["/health"]["get"]["summary"] == ""


def test_live_and_generated_fastapi_preserve_route_metadata_and_execute() -> None:
    def health() -> dict[str, str]:
        return {"status": "ok"}

    info = ToolInfo(
        name="health",
        interface_name="public-health",
        description="Tool-facing health description.",
        return_type="dict[str, str]",
        http_method="GET",
        function_body='return {"status": "ok"}',
        route_path="/health",
        operation_id="healthCheck",
        route_summary="Service health",
        route_description="Reports whether the service is ready.",
        route_tags=["operations", "public"],
        route_deprecated=True,
    )
    live: Any = build_fastapi_app("metadata", [RegisteredTool(func=health, info=info)])

    schema = ApplicationSchema.from_tools(
        name="metadata", source_type=SourceType.PYTHON, tools=(info,)
    )
    generated = ModuleType("generated_fastapi_route_metadata")
    exec(
        compile(APIGenerator().generate(schema), "<generated>", "exec"),
        generated.__dict__,
    )

    for app in (live, generated.app):
        route = _route(app, "/health")
        assert route.name == "public-health"
        assert route.operation_id == "healthCheck"
        assert route.summary == "Service health"
        assert route.description == "Reports whether the service is ready."
        assert route.tags == ["operations", "public"]
        assert route.deprecated is True

        operation = app.openapi()["paths"]["/health"]["get"]
        assert operation["operationId"] == "healthCheck"
        assert operation["summary"] == "Service health"
        assert operation["description"] == "Reports whether the service is ready."
        assert operation["tags"] == ["operations", "public"]
        assert operation["deprecated"] is True

        response = TestClient(app).get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
