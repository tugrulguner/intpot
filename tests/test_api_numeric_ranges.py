from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot


@pytest.mark.parametrize(
    "constraints", ["gt=1", "multiple_of=2", "ge=1, le=10, multiple_of=2"]
)
def test_unsupported_api_numeric_validation_is_inspectable_and_refuses_writes(
    tmp_path, constraints
):
    path = tmp_path / "unsupported.py"
    path.write_text(
        f"from fastapi import FastAPI, Query\napp=FastAPI()\n@app.get('/quote')\ndef quote(quantity: int = Query(..., {constraints})) -> int:\n    return quantity\n"
    )
    loaded = intpot.load(path)
    report = loaded.assess()
    assert len(report["diagnostics"]) == 2
    assert all(
        item["code"] == "unsupported_api_numeric_range"
        for item in report["diagnostics"]
    )
    assert loaded.schema.tools[0].parameters[0].unsupported_api_numeric_range
    for target in ("cli", "mcp"):
        for scaffold in (False, True):
            output = tmp_path / f"{target}-{scaffold}" / "app.py"
            with pytest.raises(intpot.UnsupportedAPINumericRangeError):
                loaded.write(output, target, allow_scaffold=scaffold)
            assert not output.parent.exists()


def test_dependency_refusal_precedes_numeric_range_refusal(tmp_path):
    path = tmp_path / "dependency.py"
    path.write_text(
        "from fastapi import FastAPI, Query, Depends\napp=FastAPI()\ndef check():\n    return True\n@app.get('/quote')\ndef quote(quantity: int = Query(..., gt=1), user=Depends(check)) -> int:\n    return quantity\n"
    )
    loaded = intpot.load(path)
    assert loaded.schema.tools[0].parameters[0].unsupported_api_numeric_range
    for target in ("cli", "mcp"):
        with pytest.raises(intpot.UnsupportedFastAPIDependencyError):
            loaded.project(target, allow_scaffold=True)


def test_api_application_conformance_runs_native_consumers(tmp_path):
    import json
    import subprocess
    import sys

    script = Path(__file__).parents[1] / "examples/api_application_conformance.py"
    run = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert set(report["interfaces"]) == {"source_api", "cli", "mcp"}
    source = report["interfaces"]["source_api"]["valid_results"]
    assert len(source) == 3
    for interface in report["interfaces"].values():
        assert interface["valid_results"] == source and interface["receipts_verified"]
        assert set(interface["rejections"]) == {
            "below_minimum",
            "above_maximum",
            "invalid_days",
            "invalid_replicas",
            "invalid_type",
            "missing_required",
            "business_error",
        }


def test_api_range_metadata_roundtrip_detaches_and_hashes():
    from dataclasses import replace

    from intpot.core.models import ParameterInfo, ParameterSchema, ToolInfo
    from intpot.runtime import _copy_tool_info

    parameter = ParameterInfo("quantity", "int", unsupported_api_numeric_range=True)
    schema = ParameterSchema.from_info(parameter)
    assert schema.to_dict()["unsupported_api_numeric_range"]
    assert schema == ParameterSchema.from_info(schema.to_info())
    assert schema != replace(schema, unsupported_api_numeric_range=False)
    assert len({schema, ParameterSchema.from_info(schema.to_info())}) == 1
    copied = _copy_tool_info(ToolInfo("quote", parameters=[parameter])).parameters[0]
    assert copied.unsupported_api_numeric_range
    copied.unsupported_api_numeric_range = False
    assert (
        schema.unsupported_api_numeric_range and parameter.unsupported_api_numeric_range
    )


@pytest.mark.parametrize("kind,default", [("Query", "0"), ("Query", "'2'")])
def test_unsupported_api_defaults_decline_without_inspection_failure(
    tmp_path, kind, default
):
    path = tmp_path / "defaults.py"
    path.write_text(
        f"from fastapi import FastAPI, {kind}\napp=FastAPI()\n@app.get('/quote')\ndef quote(quantity: int = {kind}({default}, ge=1, le=10)) -> int:\n    return quantity\n"
    )
    loaded = intpot.load(path)
    assert loaded.schema.tools[0].parameters[0].unsupported_api_numeric_range
    assert all(
        item["code"] == "unsupported_api_numeric_range"
        for item in loaded.assess()["diagnostics"]
    )


@pytest.mark.parametrize(
    "kind,annotation,default",
    [
        ("Query", "int", "..."),
        ("Body", "float", "..."),
        ("Header", "int", "2"),
        ("Path", "int", "..."),
    ],
)
def test_inclusive_api_bound_metadata_is_recovered(tmp_path, kind, annotation, default):
    route = "/quote/{quantity}" if kind == "Path" else "/quote"
    path = tmp_path / "bounded.py"
    default_clause = "" if default == "..." else f" = {default}"
    path.write_text(
        f"from typing import Annotated\nfrom fastapi import FastAPI, {kind}\napp=FastAPI()\n@app.post('{route}')\ndef quote(quantity: Annotated[{annotation}, {kind}(ge=1, le=10)]{default_clause}) -> {annotation}:\n    return quantity\n"
    )
    loaded = intpot.load(path)
    parameter = loaded.schema.tools[0].parameters[0]
    assert parameter.minimum == 1 and parameter.maximum == 10
    assert not parameter.unsupported_api_numeric_range
    assert loaded.project("cli").tools[0].parameters[0].minimum == 1
    assert loaded.project("mcp").tools[0].parameters[0].maximum == 10
    client = TestClient(loaded.app)

    def request(value):
        if kind == "Path":
            return client.post(f"/quote/{value}")
        if kind == "Body":
            return client.post("/quote", json=value)
        if kind == "Header":
            return client.post("/quote", headers={"quantity": str(value)})
        return client.post("/quote", params={"quantity": value})

    valid = request(2)
    assert valid.status_code == 200 and request(0).status_code == 422
    namespace = {}
    exec(loaded.to_cli(), namespace)
    prefix = ["--quantity"] if not parameter.required else []
    result = CliRunner().invoke(namespace["app"], [*prefix, "2"])
    assert result.exit_code == 0 and float(result.stdout) == valid.json()
    assert CliRunner().invoke(namespace["app"], [*prefix, "0"]).exit_code == 2


def test_storage_api_constraints_protect_the_generated_cli_body(tmp_path):
    source = Path(__file__).parents[1] / "examples/storage_quote.py"
    loaded = intpot.load(source)
    client = TestClient(loaded.app)
    receipt = tmp_path / "valid.txt"
    expected = client.get(
        "/storage-quote", params={"size_gb": 100, "receipt": str(receipt)}
    )
    assert expected.status_code == 200 and receipt.exists()
    namespace = {}
    exec(loaded.to_cli(), namespace)
    valid = CliRunner().invoke(namespace["app"], ["100"])
    assert valid.exit_code == 0, valid.exception
    assert ast.literal_eval(valid.stdout) == expected.json()
    receipt = tmp_path / "invalid.txt"
    assert (
        client.get(
            "/storage-quote", params={"size_gb": 0, "receipt": str(receipt)}
        ).status_code
        == 422
    )
    assert not receipt.exists()
    invalid = CliRunner().invoke(namespace["app"], ["0", "--receipt", str(receipt)])
    assert invalid.exit_code == 2, invalid.stdout
    assert not receipt.exists()
