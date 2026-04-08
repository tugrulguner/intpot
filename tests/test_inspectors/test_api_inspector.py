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


def test_query_param_source():
    from fastapi import Query

    from intpot.core.models import ParameterSource

    app = FastAPI()

    @app.get("/search")
    def search(q: str = Query(..., description="search term"), limit: int = Query(default=10)) -> dict:
        return {}

    inspector = APIInspector()
    tools = inspector.inspect(app)
    assert len(tools) == 1

    t = tools[0]
    q_param = next(p for p in t.parameters if p.name == "q")
    limit_param = next(p for p in t.parameters if p.name == "limit")

    assert q_param.source == ParameterSource.QUERY
    assert q_param.required
    assert q_param.description == "search term"

    assert limit_param.source == ParameterSource.QUERY
    assert limit_param.default == 10


def test_header_param_source():
    from fastapi import Header

    from intpot.core.models import ParameterSource

    app = FastAPI()

    @app.get("/protected")
    def protected(x_api_key: str = Header(...)) -> dict:
        return {}

    inspector = APIInspector()
    tools = inspector.inspect(app)
    t = tools[0]

    assert len(t.parameters) == 1
    assert t.parameters[0].source == ParameterSource.HEADER
    assert t.parameters[0].required


def test_body_param_source():
    from fastapi import Body

    from intpot.core.models import ParameterSource

    app = FastAPI()

    @app.post("/create")
    def create(name: str = Body(...), value: int = Body(default=0)) -> dict:
        return {}

    inspector = APIInspector()
    tools = inspector.inspect(app)
    t = tools[0]

    name_param = next(p for p in t.parameters if p.name == "name")
    value_param = next(p for p in t.parameters if p.name == "value")

    assert name_param.source == ParameterSource.BODY
    assert value_param.source == ParameterSource.BODY


def test_path_param_source():
    from intpot.core.models import ParameterSource

    app = FastAPI()

    @app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict:
        return {}

    inspector = APIInspector()
    tools = inspector.inspect(app)
    t = tools[0]

    assert len(t.parameters) == 1
    assert t.parameters[0].source == ParameterSource.PATH


def test_mixed_param_sources():
    from fastapi import Body, Header, Query

    from intpot.core.models import ParameterSource

    app = FastAPI()

    @app.post("/items/{item_id}")
    def create_item(
        item_id: int,
        q: str = Query(default=""),
        x_token: str = Header(...),
        payload: str = Body(...),
    ) -> dict:
        return {}

    inspector = APIInspector()
    tools = inspector.inspect(app)
    t = tools[0]

    sources = {p.name: p.source for p in t.parameters}
    assert sources["item_id"] == ParameterSource.PATH
    assert sources["q"] == ParameterSource.QUERY
    assert sources["x_token"] == ParameterSource.HEADER
    assert sources["payload"] == ParameterSource.BODY
