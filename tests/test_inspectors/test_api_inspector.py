"""Tests for the API inspector."""

from __future__ import annotations

from fastapi import FastAPI

from intpot.core.inspectors.api import APIInspector


def test_inspect_fastapi_endpoints():
    app = FastAPI()

    @app.post("/add")
    def add(a: int, b: int) -> dict:
        """Add two numbers."""
        return {"result": a + b}

    @app.post("/greet")
    def greet(name: str, greeting: str = "Hello") -> dict:
        """Greet someone."""
        return {"message": f"{greeting}, {name}!"}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    assert len(tools) == 2

    add_tool = next(t for t in tools if t.name == "add")
    assert add_tool.description == "Add two numbers."
    assert len(add_tool.parameters) == 2
    assert add_tool.parameters[0].name == "a"
    assert add_tool.parameters[0].type_annotation == "int"
    assert add_tool.parameters[0].required

    greet_tool = next(t for t in tools if t.name == "greet")
    assert greet_tool.parameters[1].name == "greeting"
    assert greet_tool.parameters[1].default == "Hello"


def test_skips_internal_routes():
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict:
        return {"msg": "hi"}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    # Should only have "hello", not openapi/swagger/redoc
    names = [t.name for t in tools]
    assert "hello" in names
    assert "openapi" not in names
    assert "swagger_ui_html" not in names
