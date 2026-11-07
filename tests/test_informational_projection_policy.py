from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import intpot
from intpot.core.callbacks import UnsupportedCLIParameterCallbackError
from intpot.core.generators.api import APIGenerator
from intpot.core.models import ApplicationSchema, SourceType


def test_projected_policy_reaches_direct_api_generation(
    monkeypatch, eager_callback_annotations
):
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    monkeypatch.syspath_prepend(str(source.parent.parent))
    monkeypatch.setenv("PYTHONPATH", str(source.parent.parent))
    loaded = intpot.load(source)
    original = loaded.schema.to_dict()
    projected = loaded.project("api", callback_policy="exclusive-informational")
    assert projected.callback_policy == "exclusive-informational"
    assert projected.to_dict()["callback_policy"] == "exclusive-informational"
    assert loaded.schema.to_dict() == original
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        APIGenerator().generate(projected.to_tools())
    code = APIGenerator().generate(projected)
    namespace: dict[str, Any] = {"__name__": "projected_information"}
    exec(code, namespace)
    with TestClient(namespace["app"]) as client:
        response = client.post("/convert", json={"version": True, "format": "invalid"})
        assert response.status_code == 200 and response.json() == {
            "result": "informational-text 1.0\n"
        }


def test_assessment_uses_explicit_callback_policy(eager_callback_annotations):
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    loaded = intpot.load(source)
    assert any(
        d["code"] == "unsupported_cli_parameter_callback"
        for d in loaded.assess()["diagnostics"]
    )
    result = loaded.assess(callback_policy="exclusive-informational")
    assert result["callback_policy"] == "exclusive-informational"
    assert result["diagnostics"] == []
    with pytest.raises(ValueError, match="Unknown callback policy"):
        loaded.assess(callback_policy="unknown")


def test_partial_policy_assessment_retains_unqualified_refusal_before_writes(
    tmp_source, callback_annotations_eager
):
    path = tmp_source("""from pathlib import Path
import typer

def info(value: bool):
    if value:
        print("INFO")
        raise typer.Exit()

def other(value: bool):
    return value

app=typer.Typer()
@app.command()
def convert(output: str, version: bool=typer.Option(False, callback=info, is_eager=True), extra: bool=typer.Option(False, callback=other, is_eager=True)):
    Path(output).write_text("body")
    typer.echo("body")
""")
    (path.parent / "__init__.py").write_text("")
    loaded = intpot.load(path)
    original = loaded.schema.to_dict()
    assessment = loaded.assess(callback_policy="exclusive-informational")
    refused = [
        item
        for item in assessment["diagnostics"]
        if item["code"] == "unsupported_cli_parameter_callback"
    ]
    expected = {"extra"} if callback_annotations_eager else {"version", "extra"}
    assert (
        len(refused) == 2 * len(expected)
        and {item["parameter"] for item in refused} == expected
    )
    target = path.parent / "not-created" / "generated.py"
    for kind in ("api", "mcp"):
        with pytest.raises(
            UnsupportedCLIParameterCallbackError,
            match="extra" if callback_annotations_eager else "version",
        ):
            loaded.write(
                target,
                kind,
                callback_policy="exclusive-informational",
                allow_scaffold=True,
            )
        assert not target.parent.exists()
    assert loaded.schema.to_dict() == original


def test_canonical_policy_validation_and_default_json_shape():
    source = ApplicationSchema("plain", SourceType.CLI, ())
    assert "callback_policy" not in source.to_dict()
    qualified = replace(
        source, callback_policy="exclusive-informational", target_type=SourceType.API
    )
    assert qualified != source and hash(qualified) == hash(replace(qualified))
    assert qualified.to_dict()["callback_policy"] == "exclusive-informational"
    with pytest.raises(ValueError, match="Unknown callback policy"):
        replace(source, callback_policy="unknown")
    with pytest.raises(ValueError):
        replace(qualified, target_type=SourceType.CLI)
