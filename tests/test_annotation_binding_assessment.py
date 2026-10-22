from __future__ import annotations

import ast
import asyncio
from typing import Any, get_args, get_type_hints

import pytest

from intpot.converter import MissingBindingError, assess_schema, project_schema
from intpot.core.models import ApplicationSchema, ParameterInfo, SourceType, ToolInfo


def test_string_helper_annotation_reports_missing_binding_before_projection():
    schema = ApplicationSchema.from_tools(
        name="annotation-consumer",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                name="double",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=[
                    "def scale(x: 'AbsentType') -> int:\n    return x * 2"
                ],
            )
        ],
    )
    assert assess_schema(schema)["diagnostics"] == [
        {
            "code": "missing_annotation_binding",
            "tool": "double",
            "target": target,
            "names": ["AbsentType"],
            "message": (
                "Generated annotation refers to bindings absent from the emitted module; "
                "provide the required import/definition or adapt the source to the supported subset."
            ),
        }
        for target in ("cli", "mcp")
    ]
    for target in (SourceType.CLI, SourceType.MCP):
        with pytest.raises(MissingBindingError, match="AbsentType"):
            project_schema(schema, target, allow_scaffold=True)


def test_postponed_public_signature_is_checked_in_emitted_cli():
    schema = ApplicationSchema.from_tools(
        name="postponed-consumer",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                name="value",
                parameters=[ParameterInfo("x", "AbsentType")],
                return_type="int",
                function_body="return 1",
            )
        ],
    )
    assert [
        (item["code"], item["target"], item["names"])
        for item in assess_schema(schema)["diagnostics"]
    ] == [
        ("missing_annotation_binding", "cli", ["AbsentType"]),
        ("missing_definition_binding", "mcp", ["AbsentType"]),
    ]
    with pytest.raises(MissingBindingError, match="AbsentType"):
        project_schema(schema, SourceType.CLI)


@pytest.mark.parametrize(
    "annotation, imports",
    [
        ('Literal["red"]', "from typing import Literal"),
        ('Choices["red"]', "from typing import Literal as Choices"),
        ('Choices["red"]', "from typing import Literal\nChoices = Literal"),
        ('t.Literal["red"]', "import typing as t"),
        ('Annotated[int, "label"]', "from typing import Annotated"),
        ('Labels[int, "label"]', "from typing import Annotated as Labels"),
        ('Annotated[int, factory("label")]', "from typing import Annotated"),
        ('factory("not a type")', ""),
        ('"broken["', ""),
    ],
)
def test_postponed_annotation_data_strings_are_not_type_references(annotation, imports):
    from intpot.core.definition_bindings import annotation_missing

    module = ast.parse(
        f"from __future__ import annotations\n{imports}\n"
        f"def f(x: {annotation}): pass\n"
        "def factory(label): return int\n"
    )
    assert annotation_missing(module) == {}


@pytest.mark.parametrize(
    "source, expected",
    [
        ('def f(x: Weird["Missing"]): pass', {"f": ["Weird"]}),
        (
            'from typing import Optional as O\ndef f(x: O["Missing"]): pass',
            {"f": ["Missing"]},
        ),
        (
            'from typing import Literal\nlist = Literal\ndef f(x: list["label"]): pass',
            {},
        ),
        ('from typing import Literal as X\nX = object\ndef f(x: X["label"]): pass', {}),
        (
            'def f(x: "A", /, *args: "B", y: "C", **kw: "D") -> "R": pass',
            {"f": ["A", "B", "C", "D", "R"]},
        ),
    ],
)
def test_annotation_unknown_roots_do_not_invent_type_positions(source, expected):
    from intpot.core.definition_bindings import annotation_missing

    assert (
        annotation_missing(ast.parse("from __future__ import annotations\n" + source))
        == expected
    )


def test_annotation_only_support_binding_does_not_satisfy_forward_reference():
    schema = ApplicationSchema.from_tools(
        name="uninitialized-annotation",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                name="value",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return helper(x)",
                support_definitions=[
                    "AbsentType: int",
                    "def helper(x: 'AbsentType') -> int:\n    return x",
                ],
            )
        ],
    )
    assert [
        (item["code"], item["target"], item["names"])
        for item in assess_schema(schema)["diagnostics"]
    ] == [
        ("missing_annotation_binding", "cli", ["AbsentType"]),
        ("missing_annotation_binding", "mcp", ["AbsentType"]),
    ]


@pytest.mark.parametrize("prefix", ["", "from __future__ import annotations\n"])
@pytest.mark.parametrize(
    "annotation, expected",
    [
        ('"Missing"', ["Missing"]),
        ('list["Missing"]', ["Missing"]),
        ('"list[\\"Missing\\"] | None"', ["Missing"]),
        ('"pkg.Type"', ["pkg"]),
        ('"Later"', []),
        ('"int"', []),
        ('Literal["Missing"]', []),
        ('Annotated["Missing", "label"]', ["Missing"]),
        ("Annotated[int, MissingMetadata]", ["MissingMetadata"]),
    ],
)
def test_annotation_lookup_uses_type_positions_and_final_module_bindings(
    prefix, annotation, expected
):
    from intpot.core.definition_bindings import annotation_missing

    module = ast.parse(
        prefix
        + "from typing import Literal, Annotated\n"
        + f"def f(x: {annotation}): pass\nLater = int\n"
    )
    # Eager non-string metadata names remain the existing definition-time check's job.
    if not prefix and annotation == "Annotated[int, MissingMetadata]":
        expected = []
    assert annotation_missing(module) == ({"f": expected} if expected else {})


@pytest.mark.parametrize("target", [SourceType.CLI, SourceType.API, SourceType.MCP])
def test_supported_annotation_strings_execute_generated_consumers(target):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from intpot.core.generators.api import APIGenerator
    from intpot.core.generators.cli import CLIGenerator
    from intpot.core.generators.mcp import MCPGenerator

    schema = ApplicationSchema.from_tools(
        name="supported-annotations",
        source_type=SourceType.CLI if target == SourceType.API else SourceType.API,
        tools=[
            ToolInfo(
                name="double",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=[
                    "from typing import Annotated as Tagged, Literal as Choice",
                    "def scale(x: Tagged['int', 'label']) -> 'int':\n    return x * 2",
                    "ChoiceValues = Choice",
                    "def label(x: ChoiceValues['red', 'blue']) -> 'str':\n    return x",
                ],
            )
        ],
    )
    assert assess_schema(schema)["diagnostics"] == []
    projected = project_schema(schema, target)
    generator = {
        SourceType.CLI: CLIGenerator,
        SourceType.API: APIGenerator,
        SourceType.MCP: MCPGenerator,
    }[target]()
    namespace: dict[str, Any] = {"__name__": "annotation_consumer"}
    exec(
        compile(
            generator.generate(projected), "<generated>", "exec", dont_inherit=True
        ),
        namespace,
    )
    hints = get_type_hints(namespace["scale"], globalns=namespace, include_extras=True)
    assert hints["return"] is int
    labels = get_type_hints(namespace["label"], globalns=namespace)
    assert get_args(labels["x"]) == ("red", "blue")
    if target == SourceType.CLI:
        result = CliRunner().invoke(namespace["app"], ["3"])
        assert result.exit_code == 0, result.exception
        assert result.stdout == "6\n"
    elif target == SourceType.API:
        response = TestClient(namespace["app"]).post("/double", json=3)
        assert response.status_code == 200, response.text
        assert response.json() == {"result": 6}
    else:
        result = asyncio.run(namespace["mcp"].call_tool("double", {"x": 3}))
        assert result.content[0].text == "6"


def test_annotation_analysis_never_evaluates_expression_calls():
    from intpot.core.definition_bindings import annotation_missing

    module = ast.parse(
        "from __future__ import annotations\n"
        "def factory(label): raise AssertionError('annotation executed')\n"
        "def f(x: factory('not a type')): pass\n"
    )
    assert annotation_missing(module) == {}


def test_shared_helper_diagnostic_is_attributed_only_to_its_owners():
    helper = "def scale(x: 'Missing') -> int:\n    return x * 2"
    tools = [
        ToolInfo(
            name=name,
            parameters=[ParameterInfo("x", "int")],
            return_type="int",
            function_body="return scale(x)" if name != "unrelated" else "return x",
            support_definitions=[helper] if name != "unrelated" else [],
        )
        for name in ("first", "second", "unrelated")
    ]
    schema = ApplicationSchema.from_tools(
        name="shared", source_type=SourceType.API, tools=tools
    )
    assert [
        (item["tool"], item["target"], item["names"])
        for item in assess_schema(schema)["diagnostics"]
    ] == [
        (name, target, ["Missing"])
        for target in ("cli", "mcp")
        for name in ("first", "second")
    ]
