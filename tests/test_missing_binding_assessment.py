from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.cli import app

MISSING = """from fastapi import FastAPI
app = FastAPI()
FACTOR = 7
def scale(x: int) -> int:
    return x * FACTOR
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
"""


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
        'from fastapi import FastAPI\napp = FastAPI()\nhelper = 7\n@app.get("/calc")\ndef calc(x: int) -> int:\n'
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
    assert {item["target"] for item in diagnostics} == {"api", "mcp"}
    assert all(item["code"] == "reference_analysis_unavailable" for item in diagnostics)
    result = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError):
        loaded.to_api(allow_scaffold=True)


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
