from __future__ import annotations

import json

from intpot.core.models import ToolInfo, ToolSchema


def test_tool_definition_location_survives_schema_adapters_and_json() -> None:
    location = ("/tmp/tool.py", 4, 9)
    info = ToolInfo("tool", source_location=location)
    schema = ToolSchema.from_info(info)
    assert schema.source_location == location
    assert schema.to_info().source_location == location
    assert schema.to_dict()["source_location"] == {
        "path": location[0],
        "line": location[1],
        "end_line": location[2],
    }
    assert hash(schema) == hash(ToolSchema.from_info(info))


def test_loaded_api_diagnostic_identifies_real_callable_definition(tmp_path) -> None:
    from typer.testing import CliRunner

    import intpot
    from intpot.cli import app

    source = tmp_path / "original.py"
    source.write_text(
        "from fastapi import FastAPI\nfrom pydantic import BaseModel\nclass Model(BaseModel):\n    value: int\napp = FastAPI()\n@app.post('/value')\ndef value(x: Model) -> int:\n    return 1\n"
    )
    loaded = intpot.load(source)
    location = {"path": str(source.resolve()), "line": 7, "end_line": 8}
    assert loaded.schema.tools[0].to_dict()["source_location"] == location
    diagnostics = loaded.assess()["diagnostics"]
    assert len(diagnostics) == 2
    assert all(item["source_location"] == location for item in diagnostics)
    result = CliRunner().invoke(app, ["inspect", str(source), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["assessment"] == loaded.assess()
    for item in diagnostics:
        for reference in item["references"]:
            expected = (
                location if reference["generated_definition"] == "_value_impl" else None
            )
            assert reference["source_location"] == expected


def test_recovered_helper_locations_survive_immutable_schema_roundtrip(
    tmp_path,
) -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    import intpot

    source = tmp_path / "helpers.py"
    source.write_text(
        "from fastapi import FastAPI\napp = FastAPI()\ndef scale(x):\n    return x * 7\n@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
    )
    tool = intpot.load(source).schema.tools[0]
    expected = (str(source.resolve()), 3, 4)
    assert tool.support_source_locations == (("scale", expected),)
    assert tool.to_info().support_source_locations == {"scale": expected}
    assert ToolSchema.from_info(tool.to_info()) == tool
    assert tool.to_dict()["support_source_locations"] == {
        "scale": {"path": expected[0], "line": 3, "end_line": 4}
    }
    with pytest.raises(FrozenInstanceError):
        tool.source_location = None


def test_locations_use_callable_owner_and_disappear_for_changed_or_dynamic_code(
    tmp_path,
) -> None:
    import importlib.util
    from dataclasses import replace

    from fastapi import FastAPI

    import intpot
    from intpot.core.provenance import callable_source_location

    path = tmp_path / "owner.py"
    path.write_text("def original(x: int) -> int:\n    return x + 1\n")
    spec = importlib.util.spec_from_file_location("provenance_owner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.get("/original")(module.original)
    schema = replace(intpot.load(app).schema, source_path=tmp_path / "unrelated.py")
    assert schema.tools[0].source_location == (str(path.resolve()), 1, 2)
    path.write_text("def original(x: int) -> int:\n    return x + 2\n")
    assert callable_source_location(module.original) is None
    namespace = {}
    exec("def dynamic(): return 1", namespace)
    assert callable_source_location(namespace["dynamic"]) is None
    assert ToolSchema("synthetic").source_location is None


def test_helper_reference_uses_own_definition_while_wrapper_has_no_original(
    tmp_path,
) -> None:
    from dataclasses import replace

    import intpot

    source = tmp_path / "helpers.py"
    source.write_text(
        "from fastapi import FastAPI\napp = FastAPI()\ndef scale(x):\n    return x * 7\n@app.get('/calc')\ndef calc(x: int) -> int:\n    return scale(x)\n"
    )
    schema = intpot.load(source).schema
    tool = schema.tools[0]
    # Explicit schema editing is supported; retained provenance denotes the
    # originating definition, never the location of this generated missing name.
    edited = replace(tool, support_definitions=("def scale(x):\n    return ABSENT",))
    report = intpot.converter.assess_schema(replace(schema, tools=(edited,)))
    helper_refs = [
        ref
        for item in report["diagnostics"]
        for ref in item.get("references", [])
        if ref["generated_definition"] == "scale"
    ]
    assert helper_refs
    assert all(
        ref["source_location"]
        == {"path": str(source.resolve()), "line": 3, "end_line": 4}
        for ref in helper_refs
    )


def test_runnable_source_provenance_example(tmp_path) -> None:
    import subprocess
    import sys
    from pathlib import Path

    example = Path(__file__).parents[1] / "examples" / "source_provenance.py"
    result = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["original_result"] == 21
    assert payload["cli_json_parity"] is True
    assert payload["refused_before_write"] is True
    assert payload["unavailable_location"] is None
