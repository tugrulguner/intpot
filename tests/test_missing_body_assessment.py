"""Public conversion refuses unrecoverable implementations, not intentional no-ops."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.cli import app

DYNAMIC = """from fastapi import FastAPI
app = FastAPI()
exec("@app.get('/unfinished')\\ndef unfinished(NotImplementedError: str = 'x') -> str:\\n    return 'source works'\\n")
"""
RECOVERED = """from fastapi import FastAPI
app = FastAPI()
@app.get('/ok')
def ok() -> str:
    return 'works'
"""


@pytest.mark.parametrize("target", ["cli", "mcp"])
def test_missing_body_assessment_refusal_and_scaffold(tmp_source, tmp_path, target):
    loaded = intpot.load(tmp_source(DYNAMIC))
    assert TestClient(loaded.app).get("/unfinished").json() == "source works"
    report = json.loads(json.dumps(loaded.assess()))
    assert not report["body_recovery_complete"]
    assert report["diagnostics"][0]["tool"] == "unfinished"
    original = loaded.schema
    with pytest.raises(intpot.MissingFunctionBodyError, match="unfinished"):
        loaded.project(target)
    with pytest.raises(intpot.MissingFunctionBodyError, match="unfinished"):
        getattr(loaded, f"to_{target}")()
    output = tmp_path / "new" / "generated.py"
    with pytest.raises(intpot.MissingFunctionBodyError):
        loaded.write(output, target)
    assert not output.parent.exists()
    code = getattr(loaded, f"to_{target}")(allow_scaffold=True)
    namespace: dict[str, Any] = {"__name__": "generated_scaffold"}
    exec(compile(code, "<generated>", "exec", dont_inherit=True), namespace)
    if target == "cli":
        result = CliRunner().invoke(namespace["app"], [])
        assert isinstance(result.exception, NotImplementedError)
        assert "Scaffold: implement tool unfinished" in str(result.exception)
    else:
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError, match="Scaffold: implement tool unfinished"):
            asyncio.run(namespace["mcp"].call_tool("unfinished", {}))
    assert loaded.schema is original
    assert loaded.schema.tools[0].function_body is None
    loaded.write(output, target, allow_scaffold=True)
    assert output.exists()


@pytest.mark.parametrize("dry_run", [False, True])
def test_directory_refuses_before_any_output(tmp_path, dry_run):
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "a_ok.py").write_text(RECOVERED)
    (sources / "z_missing.py").write_text(DYNAMIC)
    output = tmp_path / "output"
    args = ["to", "cli", str(sources), "--output", str(output)]
    if dry_run:
        args.append("--dry-run")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "unfinished" in result.output
    assert not output.exists()
    assert "Would generate" not in result.output
    opted = CliRunner().invoke(app, [*args, "--allow-scaffold"])
    assert opted.exit_code == 0, opted.output
    if dry_run:
        assert not output.exists()
        assert "Scaffold: implement tool unfinished" in opted.output
    else:
        assert (output / "a_ok_cli.py").exists()
        assert (
            "Scaffold: implement tool unfinished"
            in (output / "z_missing_cli.py").read_text()
        )


@pytest.mark.parametrize(
    "body", ["pass", "...", '"intentional no-op"', "42", "return None"]
)
def test_recovered_noops_are_not_missing(tmp_source, body):
    source = RECOVERED.replace("return 'works'", body).replace("-> str:", "-> None:")
    loaded = intpot.load(tmp_source(source))
    assert loaded.assess()["body_recovery_complete"]
    assert loaded.assess()["diagnostics"] == []
    code = loaded.to_cli()
    namespace: dict[str, Any] = {"__name__": "generated_noop"}
    exec(compile(code, "<noop>", "exec", dont_inherit=True), namespace)
    result = CliRunner().invoke(namespace["app"], [])
    assert result.exit_code == 0, result.exception
    assert "Scaffold" not in code


def test_api_scaffold_and_json_inspection(tmp_source):
    source = """import typer
app = typer.Typer()
exec("@app.command()\\ndef unfinished() -> str:\\n    return 'source works'\\n")
"""
    path = tmp_source(source)
    loaded = intpot.load(path)
    with pytest.raises(intpot.MissingFunctionBodyError, match="unfinished"):
        loaded.to_api()
    inspected = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert inspected.exit_code == 0
    assert json.loads(inspected.stdout)[0]["assessment"] == loaded.assess()
    namespace: dict[str, Any] = {"__name__": "api_scaffold"}
    exec(
        compile(loaded.to_api(allow_scaffold=True), "<api>", "exec", dont_inherit=True),
        namespace,
    )
    with pytest.raises(
        NotImplementedError, match="Scaffold: implement tool unfinished"
    ):
        TestClient(namespace["app"]).post("/unfinished")


def test_scaffold_permission_does_not_override_callbacks(tmp_source):
    source = """import typer
app = typer.Typer()
def validate(value: str) -> str:
    return value.upper()
@app.command()
def greet(name: str = typer.Option('world', callback=validate)):
    typer.echo(name)
"""
    loaded = intpot.load(tmp_source(source))
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError):
        loaded.to_api(allow_scaffold=True)
