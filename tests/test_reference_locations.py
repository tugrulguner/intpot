from __future__ import annotations

import ast
import hashlib

import pytest


@pytest.mark.parametrize("expression", ["MISSING + MISSING", "(MISSING + 1) * MISSING"])
def test_body_spans_are_original_positions_in_stable_source(tmp_path, expression):
    from intpot.core.reference_locations import body_reference_locations

    source = f"def original(x):\n    return {expression}\n"
    path = tmp_path / "original.py"
    path.write_text(source)
    emitted = ast.parse(source.replace("def original", "def _original_impl")).body[0]
    assert isinstance(emitted, ast.FunctionDef)
    locations = body_reference_locations(
        emitted, (str(path), 1, 2), hashlib.sha256(source.encode()).hexdigest()
    )
    line = source.splitlines()[1]
    columns = [line.index("MISSING"), line.rindex("MISSING")]
    assert locations is not None
    assert locations["MISSING"] == [
        {
            "path": str(path),
            "line": 2,
            "column": col + 1,
            "end_line": 2,
            "end_column": col + len("MISSING") + 1,
        }
        for col in columns
    ]


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029", "\x0b", "\x0c"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_public_ranges_use_python_physical_lines_with_unicode_comment_separators(
    tmp_path, separator, newline
):
    import json

    from typer.testing import CliRunner

    import intpot
    from intpot.cli import app

    text = (
        "from fastapi import FastAPI\n"
        "from types import SimpleNamespace\n"
        "settings = SimpleNamespace(factor=7)\n"
        "app = FastAPI()\n"
        f"# separator {separator} outside the function\n"
        "@app.get('/calc')\n"
        "def calc(x: int) -> int:\n"
        "    return x * settings.factor + settings.factor\n"
    )
    path = tmp_path / "separators.py"
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    report = intpot.load(path).assess()
    assert len(report["diagnostics"]) == 2
    line = text.split("\n")[7]
    expected_columns = [line.index("settings") + 1, line.rindex("settings") + 1]
    for diagnostic in report["diagnostics"]:
        reference = diagnostic["references"][0]
        assert reference["name"] == "settings"
        spans = reference["reference_locations"]
        assert spans is not None and len(spans) == 2
        assert [span["column"] for span in spans] == expected_columns
        for span in spans:
            assert span["line"] == span["end_line"] == 8
            assert span["end_column"] == span["column"] + len("settings")
            assert line[span["column"] - 1 : span["end_column"] - 1] == "settings"
    result = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["assessment"] == report


def test_columns_count_unicode_characters_instead_of_utf8_bytes(tmp_path):
    from intpot.core.reference_locations import body_reference_locations

    source = 'def original():\n    return "é" + MISSING\n'
    path = tmp_path / "unicode.py"
    path.write_text(source)
    emitted = ast.parse(source).body[0]
    assert isinstance(emitted, ast.FunctionDef)
    locations = body_reference_locations(
        emitted, (str(path), 1, 2), hashlib.sha256(source.encode()).hexdigest()
    )
    assert locations is not None
    column = source.splitlines()[1].index("MISSING") + 1
    assert locations["MISSING"][0]["column"] == column
    assert locations["MISSING"][0]["end_column"] == column + len("MISSING")


def test_nested_scopes_decline_attribution_instead_of_claiming_shadowed_names(tmp_path):
    from intpot.core.reference_locations import body_reference_locations

    source = "def original():\n    def nested(MISSING):\n        return MISSING\n    return MISSING\n"
    path = tmp_path / "nested.py"
    path.write_text(source)
    emitted = ast.parse(source).body[0]
    assert isinstance(emitted, ast.FunctionDef)
    assert (
        body_reference_locations(
            emitted, (str(path), 1, 4), hashlib.sha256(source.encode()).hexdigest()
        )
        is None
    )


def test_local_annotation_is_not_claimed_as_an_executed_body_load(tmp_path):
    from intpot.core.reference_locations import body_reference_locations

    source = "def original():\n    x: MISSING\n    return MISSING\n"
    path = tmp_path / "annotation.py"
    path.write_text(source)
    emitted = ast.parse(source).body[0]
    assert isinstance(emitted, ast.FunctionDef)
    locations = body_reference_locations(
        emitted, (str(path), 1, 3), hashlib.sha256(source.encode()).hexdigest()
    )
    assert locations is not None
    assert [item["line"] for item in locations["MISSING"]] == [3]


@pytest.mark.parametrize(
    "control",
    ["changed", "missing", "no_digest", "no_location", "transformed", "wrong_bounds"],
)
def test_missing_or_unmatched_original_source_stays_unavailable(tmp_path, control):
    from intpot.core.reference_locations import body_reference_locations

    source = "def original():\n    return MISSING\n"
    path = tmp_path / "control.py"
    path.write_text(source)
    emitted = ast.parse(
        source if control != "transformed" else source.replace("MISSING", "OTHER")
    ).body[0]
    assert isinstance(emitted, ast.FunctionDef)
    digest = (
        hashlib.sha256(source.encode()).hexdigest() if control != "no_digest" else None
    )
    location = (
        (str(path), 1, 2 if control != "wrong_bounds" else 3)
        if control != "no_location"
        else None
    )
    if control == "changed":
        path.write_text(source + "# unrelated source edit\n")
    if control == "missing":
        path.unlink()
    assert body_reference_locations(emitted, location, digest) is None


def test_loaded_source_reports_exact_missing_body_occurrence_and_cli_json_parity(
    tmp_path,
):
    import json

    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    import intpot
    from intpot.cli import app

    text = "from fastapi import FastAPI\nfrom types import SimpleNamespace\nsettings = SimpleNamespace(factor=7)\napp = FastAPI()\n@app.get('/calc')\ndef calc(x: int) -> int:\n    return x * settings.factor\n"
    path = tmp_path / "original.py"
    path.write_text(text)
    loaded = intpot.load(path)
    assert TestClient(loaded.app).get("/calc", params={"x": 3}).json() == 21
    report = loaded.assess()
    assert len(report["diagnostics"]) == 2
    line_number, line = next(
        (i, s) for i, s in enumerate(text.splitlines(), 1) if "return x" in s
    )
    column = line.index("settings") + 1
    expected = [
        {
            "path": str(path),
            "line": line_number,
            "column": column,
            "end_line": line_number,
            "end_column": column + len("settings"),
        }
    ]
    for item in report["diagnostics"]:
        assert item["code"] == "missing_binding"
        assert item["references"][0]["reference_locations"] == expected
    result = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["assessment"] == report
    for target in ("cli", "mcp"):
        for scaffold in (False, True):
            output = tmp_path / f"out-{target}-{scaffold}" / "app.py"
            with pytest.raises(intpot.MissingBindingError):
                loaded.write(output, target, allow_scaffold=scaffold)
            assert not output.parent.exists()


def test_cached_definition_location_survives_but_occurrences_decline_changed_file(
    tmp_path,
):
    import intpot

    text = "from fastapi import FastAPI\nfrom types import SimpleNamespace\nsettings = SimpleNamespace(factor=7)\napp = FastAPI()\n@app.get('/calc')\ndef calc(x: int) -> int:\n    return x * settings.factor\n"
    path = tmp_path / "snapshot.py"
    path.write_text(text)
    loaded = intpot.load(path)
    before = loaded.assess()["diagnostics"]
    assert before and all(
        r["reference_locations"] for d in before for r in d["references"]
    )
    path.write_text(text + "# changed after capture\n")
    after = loaded.assess()["diagnostics"]
    assert [d["source_location"] for d in after] == [
        d["source_location"] for d in before
    ]
    assert [d["names"] for d in after] == [d["names"] for d in before]
    assert all(r["reference_locations"] is None for d in after for r in d["references"])


def test_caller_assembled_helper_reference_matches_its_real_owner_not_application_path(
    tmp_path,
):
    import importlib.util
    from dataclasses import replace

    from intpot.converter import assess_schema
    from intpot.core.models import (
        ApplicationSchema,
        ParameterInfo,
        SourceType,
        ToolInfo,
    )
    from intpot.core.provenance import callable_source_metadata

    source = (
        "def scale(x):\n    return x * MISSING\ndef calc(x):\n    return scale(x)\n"
    )
    path = tmp_path / "helpers.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location("occurrence_helper", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = callable_source_metadata(module.calc)
    helper = callable_source_metadata(module.scale)
    schema = ApplicationSchema.from_tools(
        name="caller_assembled",
        source_type=SourceType.API,
        tools=[
            ToolInfo(
                "calc",
                parameters=[ParameterInfo("x", "int")],
                return_type="int",
                function_body="return scale(x)",
                support_definitions=["def scale(x):\n    return x * MISSING"],
                support_source_locations={"scale": helper["source_location"]},
                support_source_digests={"scale": helper["source_digest"]},
                **metadata,
            )
        ],
    )
    schema = replace(schema, source_path=tmp_path / "unrelated.py")
    report = assess_schema(schema)
    assert len(report["diagnostics"]) == 2
    for item in report["diagnostics"]:
        ref = item["references"][0]
        assert ref["generated_definition"] == "scale"
        assert ref["dependency_chain"] == ["calc", "_calc_impl", "scale"]
        assert ref["reference_locations"][0]["path"] == str(path)
        assert ref["reference_locations"][0]["line"] == 2
    changed = replace(
        schema.tools[0], support_definitions=("def scale(x):\n    return x * OTHER",)
    )
    altered = assess_schema(replace(schema, tools=(changed,)))
    assert all(
        r["reference_locations"] is None
        for d in altered["diagnostics"]
        for r in d["references"]
    )


def test_synthetic_and_annotation_references_have_explicit_unavailable_occurrences(
    tmp_path,
):
    import intpot

    path = tmp_path / "annotation.py"
    path.write_text(
        "from fastapi import FastAPI\nfrom pydantic import BaseModel\nclass Model(BaseModel):\n    value: int\napp = FastAPI()\n@app.post('/value')\ndef value(x: Model) -> int:\n    return 1\n"
    )
    report = intpot.load(path).assess()
    assert report["diagnostics"]
    assert all(
        r["reference_locations"] is None
        for d in report["diagnostics"]
        for r in d["references"]
    )


def test_private_alias_collision_does_not_move_original_occurrences(tmp_path):
    import intpot

    path = tmp_path / "collision.py"
    path.write_text(
        "from fastapi import FastAPI\nfrom types import SimpleNamespace\nsettings = SimpleNamespace(factor=7)\napp = FastAPI()\n@app.get('/calc')\ndef calc(x: int) -> int:\n    return x * settings.factor\n@app.get('/other')\ndef _calc_impl(x: int) -> int:\n    return x\n"
    )
    report = intpot.load(path).assess()
    assert len(report["diagnostics"]) == 2
    for item in report["diagnostics"]:
        assert item["tool"] == "calc"
        ref = item["references"][0]
        assert ref["generated_definition"].startswith("_calc_impl_")
        assert ref["reference_locations"][0]["line"] == 7
        assert ref["reference_locations"][0]["path"] == str(path)


@pytest.mark.parametrize("value", [42, [], {}, True])
def test_mutable_tool_digest_rejects_non_strings_consistently(value):
    from intpot.core.models import ToolInfo

    with pytest.raises(ValueError, match="source digest"):
        ToolInfo("invalid", source_digest=value)


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
def test_occurrence_docs_label_the_unreleased_bounded_contract(relative):
    from pathlib import Path

    text = (Path(__file__).parents[1] / relative).read_text()
    section = text.split("## Exact body-reference locations (unreleased)", 1)[1].split(
        "\n## ", 1
    )[0]
    assert "v0.15.0 does not include" in section
    assert all(
        field in section
        for field in [
            "reference_locations",
            "source_digest",
            "support_source_digests",
            "end_column",
        ]
    )
    assert "Unicode" in section and "exclusive" in section and "null" in section
    assert "caller-owned" in section and "nested scopes" in " ".join(section.split())


def test_runnable_occurrence_example(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    path = Path(__file__).parents[1] / "examples/reference_locations.py"
    result = subprocess.run(
        [sys.executable, str(path)], cwd=tmp_path, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["original_result"] == 21
    assert payload["cli_json_parity"] and payload["refused_before_write"]
    assert payload["unavailable_after_change"]
    assert payload["diagnostics"][0]["references"][0]["reference_locations"]


def test_occurrence_budget_declines_instead_of_returning_a_partial_list(tmp_path):
    from intpot.core.reference_locations import body_reference_locations

    source = "def original():\n    return " + " + ".join(["MISSING"] * 65) + "\n"
    path = tmp_path / "many.py"
    path.write_text(source)
    emitted = ast.parse(source).body[0]
    assert isinstance(emitted, ast.FunctionDef)
    assert (
        body_reference_locations(
            emitted, (str(path), 1, 2), hashlib.sha256(source.encode()).hexdigest()
        )
        is None
    )
