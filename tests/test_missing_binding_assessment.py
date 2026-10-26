from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.cli import app

MISSING = """from fastapi import FastAPI
app = FastAPI()
FACTOR = int("7")
def scale(x: int) -> int:
    return x * FACTOR
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
"""


@pytest.mark.parametrize("options", [[], ["--dry-run"], ["--allow-scaffold"]])
@pytest.mark.parametrize("target", ["cli", "mcp"])
def test_definition_time_annotation_binding_is_reported_and_refused(
    tmp_source, tmp_path, options, target
):
    source = tmp_source("""from fastapi import FastAPI
from pydantic import BaseModel
class Model(BaseModel):
    value: int
app = FastAPI()
@app.post('/value')
def value(x: Model) -> int:
    return 1
""")
    loaded = intpot.load(source)
    response = TestClient(loaded.app).post("/value", json={"value": 3})
    assert response.status_code == 200, response.text
    assert response.json() == 1
    diagnostics = loaded.assess()["diagnostics"]
    assert [(item["code"], item["target"], item["names"]) for item in diagnostics] == [
        ("missing_annotation_binding", "cli", ["Model"]),
        ("missing_definition_binding", "mcp", ["Model"]),
    ]
    with pytest.raises(intpot.MissingBindingError, match="Model"):
        loaded.project(target)
    output = tmp_path / "converted.py"
    with pytest.raises(intpot.MissingBindingError, match="Model"):
        loaded.write(output, target, allow_scaffold=True)
    assert not output.exists()
    inspection = CliRunner().invoke(app, ["inspect", str(source), "--json"])
    assert inspection.exit_code == 0, inspection.output
    assert json.loads(inspection.stdout)[0]["assessment"] == loaded.assess()
    sources = tmp_path / "mixed"
    sources.mkdir()
    (sources / "z_bad.py").write_text(source.read_text())
    (sources / "a_good.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/ok')\ndef ok() -> int:\n    return 1\n"
    )
    directory = tmp_path / "converted"
    result = CliRunner().invoke(
        app, ["to", target, str(sources), "--output", str(directory), *options]
    )
    assert result.exit_code == 1, result.output
    assert "Model" in result.stderr
    assert result.stdout == ""
    assert not directory.exists()


def test_json_inspection_reports_missing_bindings(tmp_source):
    path = tmp_source(MISSING)
    loaded = intpot.load(path)
    assert TestClient(loaded.app).get("/calc", params={"x": 3}).json() == 21
    result = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)[0]["assessment"]
    assert report == loaded.assess()
    assert report["body_recovery_complete"]
    assert {item["target"] for item in report["diagnostics"]} == {"cli", "mcp"}
    assert all(item["names"] == ["scale"] for item in report["diagnostics"])
    for target in ("cli", "mcp"):
        with pytest.raises(intpot.MissingBindingError, match="scale"):
            loaded.project(target)


@pytest.mark.parametrize("options", [[], ["--dry-run"], ["--allow-scaffold"]])
def test_directory_refusal_is_before_all_writes(tmp_path, options):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "a_good.py").write_text("""from fastapi import FastAPI
app = FastAPI()
@app.get('/ok')
def ok() -> int:
    return 1
""")
    (sources / "z_bad.py").write_text(MISSING)
    output = tmp_path / "output"
    result = CliRunner().invoke(
        app, ["to", "cli", str(sources), "--output", str(output), *options]
    )
    assert result.exit_code == 1, result.output
    assert "scale" in result.stderr
    assert result.stdout == ""
    assert not output.exists()


@pytest.mark.parametrize(
    "body, expected",
    [
        ("    return sum(i for i in range(x))\n", 3),
        (
            "    offset = 1\n    def nested(value):\n        return value + offset\n    return nested(x)\n",
            4,
        ),
        ("    from math import ceil as rounding\n    return rounding(x / 2)\n", 2),
        ("    if x <= 0:\n        return 0\n    return calc(x - 1) + 1\n", 3),
    ],
)
def test_supported_scopes_execute_generated_consumers(tmp_source, body, expected):
    path = tmp_source(
        'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/calc")\ndef calc(x: int) -> int:\n'
        + body
    )
    loaded = intpot.load(path)
    assert loaded.assess()["diagnostics"] == []
    namespace: dict[str, Any] = {"__name__": "scope_consumer"}
    exec(compile(loaded.to_cli(), "<cli>", "exec", dont_inherit=True), namespace)
    result = CliRunner().invoke(namespace["app"], ["3"])
    assert result.exit_code == 0, result.exception
    assert result.stdout.strip() == str(expected)
    namespace = {"__name__": "scope_mcp"}
    exec(compile(loaded.to_mcp(), "<mcp>", "exec", dont_inherit=True), namespace)
    assert asyncio.run(namespace["mcp"].call_tool("calc", {"x": 3})).content[
        0
    ].text == str(expected)


@pytest.mark.parametrize(
    "body",
    [
        "    def unrelated():\n        helper = 2\n        return helper\n    return helper + x\n",
        "    values = [helper for helper in range(x)]\n    return helper\n",
        "    def nested():\n        return helper + x\n    return nested()\n",
    ],
)
def test_shadowed_names_do_not_hide_missing_globals(tmp_source, body):
    path = tmp_source(
        'from fastapi import FastAPI\napp = FastAPI()\nhelper = int("7")\n@app.get("/calc")\ndef calc(x: int) -> int:\n'
        + body
    )
    loaded = intpot.load(path)
    assert all(item["names"] == ["helper"] for item in loaded.assess()["diagnostics"])
    with pytest.raises(intpot.MissingBindingError, match="helper"):
        loaded.to_cli()


def test_unavailable_reference_analysis_is_explicit_and_inspection_survives(tmp_source):
    path = tmp_source("""import typer
app = typer.Typer(add_completion=False)
def validate(value):
    return value
@app.command()
def run(x: str = typer.Option('ok', callback=validate)):
    typer.echo(x)
""")
    loaded = intpot.load(path)
    diagnostics = loaded.assess()["diagnostics"]
    assert not any(
        item["code"] == "reference_analysis_unavailable" for item in diagnostics
    )
    assert {item["code"] for item in diagnostics} == {
        "unsupported_cli_parameter_callback"
    }
    result = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError):
        loaded.to_api(allow_scaffold=True)


def test_callback_and_dependency_refusals_are_structured_and_skip_reference_analysis(
    tmp_source,
):
    callback = tmp_source("""import typer
app = typer.Typer(add_completion=False)
def reject(value):
    if value == "bad": raise typer.BadParameter("rejected by source")
    return value
@app.command()
def alpha(first: str = typer.Option("ok", callback=reject), second: str = typer.Option("x", callback=reject)):
    typer.echo(first + second)
@app.command()
def beta(value: int):
    typer.echo(value)
""")
    loaded = intpot.load(callback)
    original = CliRunner().invoke(loaded.app, ["alpha", "--first", "bad"])
    assert original.exit_code != 0
    assert "rejected by source" in original.output
    report = loaded.assess()
    refused = [
        item
        for item in report["diagnostics"]
        if item["code"] == "unsupported_cli_parameter_callback"
    ]
    assert {(item["tool"], item["parameter"], item["target"]) for item in refused} == {
        ("alpha", "first", "api"),
        ("alpha", "first", "mcp"),
        ("alpha", "second", "api"),
        ("alpha", "second", "mcp"),
    }
    assert all(
        item["reference_analysis"] == "skipped_due_to_refusal" for item in refused
    )
    assert all(
        "would be lost without equivalent implementation; conversion is refused"
        in item["consequence"]
        for item in refused
    )
    assert not any(
        item["code"] == "reference_analysis_unavailable"
        for item in report["diagnostics"]
    )
    inspected = CliRunner().invoke(app, ["inspect", str(callback), "--json"])
    assert json.loads(inspected.stdout)[0]["assessment"] == report

    api = tmp_source("""from fastapi import FastAPI, Depends
app = FastAPI()
def check(): return "executed"
@app.get("/value", name="value_route")
def value(token: str = Depends(check)):
    return {"token": token}
""")
    loaded_api = intpot.load(api)
    assert TestClient(loaded_api.app).get("/value").json() == {"token": "executed"}
    diagnostics = loaded_api.assess()["diagnostics"]
    assert {
        (item["tool"], item["target"])
        for item in diagnostics
        if item["code"] == "unsupported_fastapi_dependency"
    } == {("value", "cli"), ("value", "mcp")}
    assert not any(
        item["code"] == "reference_analysis_unavailable" for item in diagnostics
    )
    dep_refused = [
        item for item in diagnostics if item["code"] == "unsupported_fastapi_dependency"
    ]
    assert all(
        item["reference_analysis"] == "skipped_due_to_refusal" for item in dep_refused
    )
    assert all(
        item["route"] == {"path": "/value", "operation_id": None, "name": "value_route"}
        for item in dep_refused
    )
    assert all(
        "would be lost without equivalent implementation; conversion is refused"
        in item["consequence"]
        for item in dep_refused
    )
    inspected = CliRunner().invoke(app, ["inspect", str(api), "--json"])
    assert json.loads(inspected.stdout)[0]["assessment"] == loaded_api.assess()


@pytest.mark.parametrize("allow_scaffold", [False, True])
@pytest.mark.parametrize("kind", ["callback", "dependency"])
def test_refusal_diagnostics_precede_writes_even_with_scaffold(
    tmp_source, tmp_path, kind, allow_scaffold
):
    text = (
        "import typer\napp = typer.Typer()\ndef check(v): return v\n"
        "@app.command()\ndef run(v: str = typer.Option('x', callback=check)): typer.echo(v)"
        if kind == "callback"
        else "from fastapi import FastAPI, Depends\napp = FastAPI()\ndef check(): return 'x'\n"
        "@app.get('/x')\ndef run(v: str = Depends(check)): return {'v': v}"
    )
    loaded = intpot.load(tmp_source(text))
    output = tmp_path / "out.py"
    error = (
        intpot.UnsupportedCLIParameterCallbackError
        if kind == "callback"
        else intpot.UnsupportedFastAPIDependencyError
    )
    with pytest.raises(error):
        loaded.write(
            output,
            "api" if kind == "callback" else "cli",
            allow_scaffold=allow_scaffold,
        )
    assert not output.exists()


def test_non_api_dependency_metadata_does_not_trigger_fastapi_refusal(tmp_source):
    path = tmp_source(MISSING)
    loaded = intpot.load(path)
    schema = replace(
        loaded.schema,
        source_type=intpot.SourceType.CLI,
        tools=(replace(loaded.schema.tools[0], dependencies=("metadata_only",)),),
    )
    report = intpot.converter.assess_schema(schema)
    assert not any(
        item["code"] == "unsupported_fastapi_dependency"
        for item in report["diagnostics"]
    )


def test_conversion_refusals_example_executes(capsys):
    import runpy

    example = (
        Path(__file__).resolve().parents[1] / "examples" / "conversion_refusals.py"
    )
    runpy.run_path(str(example), run_name="__main__")
    output = capsys.readouterr().out
    assert "unsupported_cli_parameter_callback" in output
    assert "unsupported_fastapi_dependency" in output
    assert "both conversions refused before output" in output


def test_directory_inspection_json_matches_each_source_assessment(tmp_source, tmp_path):
    first = tmp_source("""import typer
app = typer.Typer()
def check(v): return v
@app.command()
def run(v: str = typer.Option('x', callback=check)): typer.echo(v)
""")
    second = tmp_source("""from fastapi import FastAPI, Depends
app = FastAPI()
def check(): return 'x'
@app.get('/x')
def run(v: str = Depends(check)): return {'v': v}
""")
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "alpha.py").write_text(first.read_text())
    (sources / "beta.py").write_text(second.read_text())
    inspected = CliRunner().invoke(app, ["inspect", str(sources), "--json"])
    assert inspected.exit_code == 0, inspected.output
    payload = json.loads(inspected.stdout)
    assert [Path(item["source"]).name for item in payload] == ["alpha.py", "beta.py"]
    for item in payload:
        source = sources / Path(item["source"]).name
        loaded = intpot.load(source)
        assert item["tools"] == loaded.schema.to_dict()["tools"]
        assert item["assessment"] == loaded.assess()


@pytest.mark.parametrize(
    "binding",
    [
        "__file__",
        "__name__",
        "__package__",
        "__spec__",
        "__loader__",
        "__cached__",
        "__doc__",
        "__builtins__",
    ],
)
def test_file_loader_bindings_execute_generated_consumers(
    tmp_source, tmp_path, binding
):
    import importlib.util

    source = tmp_source(
        "from fastapi import FastAPI\napp = FastAPI()\n"
        "@app.get('/module')\ndef module() -> str:\n"
        f"    return str({binding})\n"
    )
    loaded = intpot.load(source)
    assert loaded.assess()["diagnostics"] == []
    for target in ("cli", "mcp"):
        path = tmp_path / f"generated_{target}.py"
        loaded.write(path, target)
        spec = importlib.util.spec_from_file_location(f"loader_{target}", path)
        assert spec is not None and spec.loader is not None
        generated = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generated)
        expected = str(getattr(generated, binding))
        if target == "cli":
            result = CliRunner().invoke(generated.app, [])
            assert result.exit_code == 0, result.exception
            assert result.stdout.rstrip("\n") == expected
        else:
            result = asyncio.run(generated.mcp.call_tool("module", {}))
            assert result.content[0].text == expected
        if binding == "__file__":
            assert expected == str(path)
            assert expected != str(source)


def test_package_only_and_similarly_named_bindings_remain_missing(tmp_source):
    source = tmp_source(
        "from fastapi import FastAPI\napp = FastAPI()\n"
        "@app.get('/module')\ndef module() -> str:\n"
        "    return str(__path__) + str(__file_like__)\n"
    )
    loaded = intpot.load(source)
    assert all(
        item["names"] == ["__file_like__", "__path__"]
        for item in loaded.assess()["diagnostics"]
    )
    with pytest.raises(intpot.MissingBindingError, match="__path__"):
        loaded.to_cli()
