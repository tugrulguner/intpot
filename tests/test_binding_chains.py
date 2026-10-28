from __future__ import annotations

import json
from typing import Any

import pytest

from intpot.converter import assess_schema
from intpot.core.models import ApplicationSchema, ParameterInfo, SourceType, ToolInfo


def test_body_reference_explains_tool_to_helper_dependency_chain():
    schema = ApplicationSchema.from_tools(
        name="chains",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=["def scale(x):\n    return x * MISSING"],
            )
        ],
    )
    report = assess_schema(schema)
    diagnostics = [
        item for item in report["diagnostics"] if item["code"] == "missing_binding"
    ]
    assert {item["target"] for item in diagnostics} == {"cli", "mcp"}
    for diagnostic in diagnostics:
        assert diagnostic["names"] == ["MISSING"]
        assert diagnostic["references"] == [
            {
                "name": "MISSING",
                "generated_definition": "scale",
                "reference_locations": None,
                "dependency_chain": ["calc", "_calc_impl", "scale"],
            }
        ]
    assert json.loads(json.dumps(report)) == report


def test_rebound_helper_has_no_claimed_dependency_chain():
    schema = ApplicationSchema.from_tools(
        name="rebound",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="global scale\nscale = lambda x: x\nreturn scale(x)",
                support_definitions=["def scale(x):\n    return x * MISSING"],
            )
        ],
    )
    diagnostics = assess_schema(schema)["diagnostics"]
    assert diagnostics
    for diagnostic in diagnostics:
        reference = next(
            ref
            for ref in diagnostic["references"]
            if ref["generated_definition"] == "scale"
        )
        assert reference["dependency_chain"] is None


def test_unanalyzable_function_does_not_add_an_assessment_exception():
    schema = ApplicationSchema.from_tools(
        name="unknown",
        source_type=SourceType.API,
        tools=[ToolInfo("calc", function_body="nonlocal MISSING\nreturn MISSING")],
    )
    report = assess_schema(schema)
    assert report["diagnostics"]
    for diagnostic in report["diagnostics"]:
        assert diagnostic["code"] == "missing_binding"
        assert diagnostic["references"][0]["dependency_chain"] is None


def test_transitive_recursive_paths_choose_one_shortest_lexically_sorted_route():
    schema = ApplicationSchema.from_tools(
        name="diamond",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return zed(x) + alpha(x)",
                support_definitions=[
                    "def zed(x):\n    return leaf(x)",
                    "def alpha(x):\n    return leaf(x)",
                    "def leaf(x):\n    return MISSING if x else alpha(x)",
                ],
            )
        ],
    )
    original_hash = hash(schema)
    first = assess_schema(schema)
    assert len(first["diagnostics"]) == 2
    for item in first["diagnostics"]:
        assert item["references"] == [
            {
                "name": "MISSING",
                "generated_definition": "leaf",
                "reference_locations": None,
                "dependency_chain": ["calc", "_calc_impl", "alpha", "leaf"],
            }
        ]
    assert hash(schema) == original_hash
    assert assess_schema(schema) == first
    first["diagnostics"][0]["references"][0]["dependency_chain"].append("mutated")
    assert assess_schema(schema) != first


@pytest.mark.parametrize(
    "body", ["return 0", "scale = lambda x: x\nreturn scale(x)", "return x.scale()"]
)
def test_unreachable_or_shadowed_helpers_remain_unresolved(body):
    schema = ApplicationSchema.from_tools(
        name="unresolved",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body=body,
                support_definitions=["def scale(x):\n    return MISSING"],
            )
        ],
    )
    report = assess_schema(schema)
    assert report["diagnostics"]
    assert all(
        ref["dependency_chain"] is None
        for item in report["diagnostics"]
        for ref in item["references"]
    )


def test_private_name_collision_uses_emitted_alias_without_other_tool_attribution():
    schema = ApplicationSchema.from_tools(
        name="collision",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=["def scale(x):\n    return MISSING"],
            ),
            ToolInfo(
                "_calc_impl",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return x",
            ),
        ],
    )
    report = assess_schema(schema)
    assert report["diagnostics"]
    for item in report["diagnostics"]:
        assert item["tool"] == "calc"
        chain = item["references"][0]["dependency_chain"]
        assert len(chain) == 3 and chain[0] == "calc" and chain[-1] == "scale"
        assert chain[1].startswith("_calc_impl_") and "_calc_impl" not in chain


def test_real_source_cli_json_paths_keep_wrapper_origin_unavailable(tmp_path):
    from typer.testing import CliRunner

    import intpot
    from intpot.cli import app

    source = tmp_path / "original.py"
    source.write_text(
        "from fastapi import FastAPI\nfrom pydantic import BaseModel\nclass Model(BaseModel):\n    value: int\napp = FastAPI()\n@app.post('/value')\ndef value(x: Model) -> int:\n    return 1\n"
    )
    loaded = intpot.load(source)
    report = loaded.assess()
    assert report["diagnostics"]
    for item in report["diagnostics"]:
        for ref in item["references"]:
            if ref["generated_definition"] == "value":
                assert ref["dependency_chain"] == ["value"]
                assert ref["source_location"] is None
            else:
                assert ref["dependency_chain"] == ["value", "_value_impl"]
                assert ref["source_location"] == {
                    "path": str(source.resolve()),
                    "line": 7,
                    "end_line": 8,
                }
    result = CliRunner().invoke(app, ["inspect", str(source), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["assessment"] == report


def test_explanation_does_not_change_successful_generation():
    from intpot.core.generators.cli import CLIGenerator

    schema = ApplicationSchema.from_tools(
        name="good",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=["def scale(x):\n    return x * 7"],
            ),
        ],
    )
    generated = CLIGenerator().generate(schema)
    assert assess_schema(schema)["diagnostics"] == []
    assert CLIGenerator().generate(schema) == generated
    from typer.testing import CliRunner

    namespace: dict[str, Any] = {"__name__": "binding_chain_consumer"}
    exec(compile(generated, "<binding-chain-consumer>", "exec"), namespace)
    result = CliRunner().invoke(namespace["app"], ["3"])
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "21"


def test_runnable_binding_chain_example(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    example = Path(__file__).parents[1] / "examples/binding_chains.py"
    result = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["original_http_result"] == 21
    assert payload["generated_cli_result"] == 21
    assert payload["fixture_kind"] == "caller-authored incomplete schema"
    assert payload["cli_json_parity"] and payload["refused_before_write"]


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "website/src/content/docs/conversion-boundaries.md",
        "website/src/content/docs/schema-reference.md",
        "src/intpot/templates/skills/intpot-cli.md",
        "src/intpot/templates/skills/intpot-python.md",
    ],
)
def test_chain_contract_requires_v015_and_remains_static(relative):
    from pathlib import Path

    text = (Path(__file__).parents[1] / relative).read_text()
    section = text.split("## Bounded binding chains (v0.15.0)", 1)[1].split("\n## ", 1)[
        0
    ]
    assert "requires v0.15.0 or newer" in section
    assert "dependency_chain" in section and "v0.14.0 does not include" in section
    assert "shortest" in section and "null" in section
    assert "not an execution trace" in section
    assert "caller-authored" in section
