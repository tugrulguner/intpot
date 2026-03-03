"""Tests for the API generator."""

from __future__ import annotations

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
    assert "from pydantic import BaseModel" in code
    assert "class AddRequest(BaseModel):" in code
    assert 'app.post("/add")' in code
    assert "def add(request: AddRequest)" in code


def test_generate_no_params():
    tools = [
        ToolInfo(name="ping", description="Ping.", parameters=[]),
    ]

    code = APIGenerator().generate(tools)
    assert "def ping()" in code
    assert "AddRequest" not in code
