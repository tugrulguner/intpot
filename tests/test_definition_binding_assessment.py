from __future__ import annotations

import ast
import asyncio
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from intpot.converter import MissingBindingError, assess_schema, project_schema
from intpot.core.definition_bindings import (
    definition_time_missing as _definition_time_missing,
)
from intpot.core.models import ApplicationSchema, ParameterInfo, SourceType, ToolInfo


def helper_schema(definitions):
    return ApplicationSchema.from_tools(
        name="definition-consumer",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                name="calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=list(definitions),
            )
        ],
    )


@pytest.mark.parametrize("target", [SourceType.CLI, SourceType.MCP])
def test_helper_default_requires_binding_before_definition(target):
    schema = helper_schema(
        ["def scale(x, factor=LATER):\n    return x * factor", "LATER = 7"]
    )
    diagnostics = assess_schema(schema)["diagnostics"]
    assert any(
        item["code"] == "missing_definition_binding"
        and item["tool"] == "calc"
        and item["target"] == target.value
        and item["names"] == ["LATER"]
        for item in diagnostics
    )
    with pytest.raises(MissingBindingError, match="LATER"):
        project_schema(schema, target, allow_scaffold=True)


@pytest.mark.parametrize(
    "expression", ["[x for x in range(3)]", "lambda x: x + missing_later"]
)
def test_eager_expression_scopes_do_not_load_deferred_or_local_names(expression):
    module = ast.parse(f"def scale(value={expression}):\n    return value\n")
    assert _definition_time_missing(module) == {}


@pytest.mark.parametrize(
    "target", list((SourceType.CLI, SourceType.API, SourceType.MCP))
)
def test_ordered_helper_default_executes_generated_consumer(target):
    from intpot.core.generators.api import APIGenerator
    from intpot.core.generators.cli import CLIGenerator
    from intpot.core.generators.mcp import MCPGenerator

    schema = helper_schema(
        ["FACTOR = 7", "def scale(x, factor=FACTOR):\n    return x * factor"]
    )
    if target == SourceType.API:
        schema = replace(schema, source_type=SourceType.CLI)
    projected = project_schema(schema, target)
    generator = {
        SourceType.CLI: CLIGenerator,
        SourceType.API: APIGenerator,
        SourceType.MCP: MCPGenerator,
    }[target]()
    namespace: dict[str, Any] = {"__name__": "definition_consumer"}
    exec(
        compile(
            generator.generate(projected), "<generated>", "exec", dont_inherit=True
        ),
        namespace,
    )
    if target == SourceType.CLI:
        result = CliRunner().invoke(namespace["app"], ["3"])
        assert result.exit_code == 0, result.exception
        assert result.stdout == "21\n"
    elif target == SourceType.API:
        response = TestClient(namespace["app"]).post("/calc", json=3)
        assert response.status_code == 200, response.text
        assert response.json() == {"result": 21}
    else:
        result = asyncio.run(namespace["mcp"].call_tool("calc", {"x": 3}))
        assert result.content[0].text == "21"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("def f(x: Missing): pass", {"f": ["Missing"]}),
        ("def f(*args: Missing, **kw: Other): pass", {"f": ["Missing", "Other"]}),
        ("def f(*, x=Missing): pass", {"f": ["Missing"]}),
        ("@decorator\ndef f(): pass", {"f": ["decorator"]}),
        ("from __future__ import annotations\ndef f(x: Missing): pass", {}),
        ("from math import ceil as rounding\ndef f(x=rounding(3.1)): pass", {}),
        ("def f(x=f): pass", {"f": ["f"]}),
        ("def f(): return later()\ndef later(): return 1", {}),
        (
            "def f(x=(value for value in missing_iterable)): pass",
            {"f": ["missing_iterable"]},
        ),
    ],
)
def test_definition_binding_evaluation_boundaries(source, expected):
    assert _definition_time_missing(ast.parse(source)) == expected


def test_annotation_only_statement_does_not_initialize_binding():
    module = ast.parse("FACTOR: int\ndef scale(value=FACTOR):\n    return value\n")
    assert _definition_time_missing(module) == {"scale": ["FACTOR"]}
