from __future__ import annotations

import json
from pathlib import Path

import pytest

from intpot.converter import MissingBindingError, assess_schema, project_schema
from intpot.core.models import ApplicationSchema, ParameterInfo, SourceType, ToolInfo


@pytest.mark.parametrize("target", [SourceType.CLI, SourceType.MCP])
def test_body_context_names_each_emitted_owner_without_inventing_source_location(
    target, tmp_path
):
    # An application path is not evidence of a recovered callable/helper location.
    source = tmp_path / "unrelated.py"
    source.write_text("def calc(x):\n    return 42\n")
    schema = ApplicationSchema.from_tools(
        name="context",
        source_type=SourceType.API,
        source_path=source,
        tools=[
            ToolInfo(
                name="calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x) + MISSING",
                support_definitions=["def scale(x):\n    return x * MISSING"],
            )
        ],
    )
    report = assess_schema(schema)
    diagnostic = next(
        item for item in report["diagnostics"] if item["target"] == target.value
    )
    assert diagnostic["code"] == "missing_binding"
    assert diagnostic["tool"] == "calc"
    assert diagnostic["names"] == ["MISSING"]
    assert diagnostic["source_location"] is None
    assert diagnostic["references"] == [
        {
            "name": "MISSING",
            "generated_definition": "_calc_impl",
            "reference_locations": None,
            "dependency_chain": ["calc", "_calc_impl"],
        },
        {
            "name": "MISSING",
            "generated_definition": "scale",
            "reference_locations": None,
            "dependency_chain": ["calc", "_calc_impl", "scale"],
        },
    ]
    assert diagnostic["suggested_action"] == (
        "Import or define MISSING in the generated module before use, "
        "or adapt the source to the supported subset."
    )
    assert json.loads(json.dumps(report)) == report
    assert assess_schema(schema) == report
    with pytest.raises(MissingBindingError, match="calc: MISSING"):
        project_schema(schema, target, allow_scaffold=True)
    assert source.read_text() == "def calc(x):\n    return 42\n"


def test_inspect_json_exposes_the_same_context_as_python_without_source_guessing(
    tmp_path,
):
    from typer.testing import CliRunner

    import intpot
    from intpot.cli import app

    source = tmp_path / "api.py"
    source.write_text(
        "from fastapi import FastAPI\nfrom pydantic import BaseModel\n"
        "class Model(BaseModel):\n    value: int\n"
        "app = FastAPI()\n@app.post('/value')\n"
        "def value(x: Model) -> int:\n    return 1\n"
    )
    loaded = intpot.load(source)
    assessment = loaded.assess()
    result = CliRunner().invoke(app, ["inspect", str(source), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["assessment"] == assessment
    assert len(assessment["diagnostics"]) == 2
    for item in assessment["diagnostics"]:
        assert item["source_location"] == {
            "path": str(source.resolve()),
            "line": 7,
            "end_line": 8,
        }
        assert item["references"]
        assert {ref["name"] for ref in item["references"]} == {"Model"}
        assert "Model" in item["suggested_action"]
        output = tmp_path / item["target"] / "app.py"
        with pytest.raises(MissingBindingError, match="value: Model"):
            loaded.write(output, item["target"], allow_scaffold=True)
        assert not output.parent.exists()


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
def test_diagnostic_context_docs_do_not_advertise_fields_in_published_v012(relative):
    text = (Path(__file__).parents[1] / relative).read_text()
    section = text.split("## Actionable binding context", 1)[1].split("\n## ", 1)[0]
    for field in ("references", "suggested_action", "source_location"):
        assert field in section
    assert "v0.13.0" in section
    assert "until" in section.lower()
    assert "v0.12.0" in section
    assert "not included" in section or "does not include" in section
    assert "coordinates" in section


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
def test_provenance_docs_pin_v014_availability_without_relabelling_v013(relative):
    text = (Path(__file__).parents[1] / relative).read_text()
    section = text.split("## Bounded definition provenance", 1)[1].split("\n## ", 1)[0]
    assert section.startswith(" (v0.14.0)")
    assert "requires v0.14.0 or newer" in section
    assert "until v0.14.0 is published" in section
    assert "v0.13.0 does not" in section
    for field in ("source_location", "support_source_locations", "end_line"):
        assert field in section
    assert "inspection snapshot" in section
    assert "synthetic" in section.lower()


@pytest.mark.parametrize("filename", ["diagnostic_context.py", "source_provenance.py"])
def test_location_asserting_examples_state_v014_requirement(filename):
    import ast

    source = Path(__file__).parents[1] / "examples" / filename
    doc = ast.get_docstring(ast.parse(source.read_text()))
    assert doc is not None
    assert "requires v0.14.0 or newer" in doc
    assert "unreleased source checkout only" not in doc
