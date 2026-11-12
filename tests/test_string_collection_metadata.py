from __future__ import annotations

import pytest

from intpot.core.models import ParameterInfo, ParameterSchema, ToolInfo
from intpot.runtime import RegisteredTool


def test_string_collection_metadata_round_trips_projection_and_json():
    absent = ParameterInfo("values", type_annotation="list[str]")
    present = ParameterInfo("values", type_annotation="list[str]", minimum_items=1)

    absent_schema = ParameterSchema.from_info(absent)
    present_schema = ParameterSchema.from_info(present)

    assert "minimum_items" not in absent_schema.to_dict()
    assert present_schema.to_dict()["minimum_items"] == 1
    assert ParameterSchema.from_info(present_schema.to_info()) == present_schema
    assert hash(ParameterSchema.from_info(present_schema.to_info())) == hash(
        present_schema
    )


def test_string_collection_metadata_default_validation():
    with pytest.raises(ValueError, match="default"):
        ParameterInfo(
            "values", type_annotation="list[str]", default=[], minimum_items=1
        )


def test_fastapi_live_builder_rejects_empty_marked_string_collection():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from intpot.runtime_builders import build_fastapi_app

    def collect(values: list[str]) -> int:
        return len(values)

    tool = RegisteredTool(
        func=collect,
        info=ToolInfo(
            name="collect",
            parameters=[
                ParameterInfo("values", type_annotation="list[str]", minimum_items=1)
            ],
        ),
    )
    app = build_fastapi_app("test", [tool])
    assert isinstance(app, FastAPI)
    response = TestClient(app).post("/collect", json=[])

    assert response.status_code == 422


def test_fastapi_live_builder_accepts_nonempty_marked_string_collection():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from intpot.runtime_builders import build_fastapi_app

    def collect(values: list[str]) -> int:
        return len(values)

    tool = RegisteredTool(
        func=collect,
        info=ToolInfo(
            name="collect",
            parameters=[
                ParameterInfo("values", type_annotation="list[str]", minimum_items=1)
            ],
        ),
    )
    app = build_fastapi_app("test", [tool])
    assert isinstance(app, FastAPI)
    response = TestClient(app).post("/collect", json=["one"])

    assert response.status_code == 200, response.text
    assert response.json() == 1


def test_mcp_live_builder_honors_explicit_minimum_items_before_call():
    import asyncio

    from fastmcp import Client, FastMCP
    from fastmcp.exceptions import ToolError

    from intpot.runtime_builders import build_fastmcp_app

    seen: list[list[str]] = []

    def collect(values: list[str]) -> int:
        seen.append(values)
        return len(values)

    tool = RegisteredTool(
        func=collect,
        info=ToolInfo(
            name="collect",
            parameters=[
                ParameterInfo("values", type_annotation="list[str]", minimum_items=1)
            ],
        ),
    )
    app = build_fastmcp_app("marked-list", [tool])
    assert isinstance(app, FastMCP)

    async def exercise():
        async with Client(app) as client:
            with pytest.raises(ToolError):
                await client.call_tool("collect", {"values": []})
            assert seen == []
            result = await client.call_tool("collect", {"values": ["one"]})
            assert not result.is_error
            assert seen == [["one"]]

    asyncio.run(exercise())
