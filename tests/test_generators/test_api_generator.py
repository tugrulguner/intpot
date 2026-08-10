"""Tests for the API generator."""

from __future__ import annotations

from typing import Any

from intpot.core.generators.api import APIGenerator
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def test_generate_api_app():
    tools = [
        ToolInfo(
            name="add",
            description="Add two numbers.",
            parameters=[
                ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
                ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
            ],
            return_type="int",
        ),
    ]

    code = APIGenerator().generate(tools)

    assert "from fastapi import FastAPI" in code
    assert "Body" in code
    assert 'app.post("/add")' in code
    assert "def add(" in code
    assert "a: int" in code
    assert "b: int" in code


def test_generate_no_params():
    tools = [
        ToolInfo(name="ping", description="Ping.", parameters=[]),
    ]

    code = APIGenerator().generate(tools)
    assert "def ping()" in code


def _add_tool(function_body: str | None) -> ToolInfo:
    return ToolInfo(
        name="add",
        description="Add two numbers.",
        parameters=[
            ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
            ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
        ],
        return_type="int",
        function_body=function_body,
    )


def test_preserved_body_keeps_its_own_return_type():
    """A preserved body returns the tool's real type, so annotate it as such.

    Annotating `-> dict` made FastAPI validate the response against dict and
    reject anything else at runtime.
    """
    code = APIGenerator().generate([_add_tool("return a + b")])

    assert ") -> int:" in code
    assert ") -> dict:" not in code


def test_stub_body_is_still_a_dict():
    """Without a body the stub returns {"result": ...}, so `-> dict` is correct."""
    code = APIGenerator().generate([_add_tool(None)])

    assert ") -> dict:" in code


def test_generated_app_serves_a_real_request():
    """Execute the generated module and call it — a string check would not catch
    a ResponseValidationError."""
    from fastapi.testclient import TestClient

    code = APIGenerator().generate([_add_tool("return a + b")])
    namespace: dict[str, Any] = {}
    exec(compile(code, "<generated>", "exec"), namespace)

    response = TestClient(namespace["app"]).post("/add", json={"a": 2, "b": 3})

    assert response.status_code == 200
    assert response.json() == 5
