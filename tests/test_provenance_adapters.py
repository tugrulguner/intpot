from __future__ import annotations

import json
from typing import Any, cast

import pytest

import intpot
from intpot.core.models import ToolInfo, ToolSchema


def test_schema_detaches_and_freezes_source_locations():
    location: list[Any] = ["/tmp/tool.py", 2, 5]
    helper: list[Any] = ["/tmp/tool.py", 8, 9]
    info = ToolInfo(
        name="x",
        source_location=cast(Any, location),
        support_source_locations={"helper": cast(Any, helper)},
    )
    schema = ToolSchema.from_info(info)
    location[0] = "changed"
    helper[1] = 0
    assert schema.source_location == ("/tmp/tool.py", 2, 5)
    assert schema.support_source_locations == (("helper", ("/tmp/tool.py", 8, 9)),)
    with pytest.raises(TypeError):
        cast(Any, schema.source_location)[0] = "changed"
    assert hash(schema) == hash(ToolSchema.from_info(schema.to_info()))


@pytest.mark.parametrize(
    "location", [("", 0, 1), ("file.py", True, 2), ("file.py", 5, 4), ("file.py", 1)]
)
def test_schema_rejects_invalid_source_location(location):
    with pytest.raises((TypeError, ValueError)):
        ToolSchema(name="x", source_location=location)


def test_info_schema_json_roundtrip_source_metadata():
    info = ToolInfo(
        name="x",
        source_location=("/tmp/tool.py", 2, 5),
        support_source_locations={"helper": ("/tmp/tool.py", 8, 9)},
    )
    schema = ToolSchema.from_info(info)
    rebuilt = ToolSchema.from_info(schema.to_info())
    detached = rebuilt.to_info()
    detached.support_source_locations["helper"] = ("changed", 1, 1)
    assert rebuilt == schema
    assert json.loads(json.dumps(rebuilt.to_dict())) == schema.to_dict()
    assert schema.to_dict()["source_location"] == {
        "path": "/tmp/tool.py",
        "line": 2,
        "end_line": 5,
    }


@pytest.mark.parametrize("framework", ["cli", "mcp", "python"])
def test_file_backed_inspection_captures_callable_metadata(tmp_path, framework):
    headers = {
        "cli": "import typer\napp = typer.Typer()\n@app.command()\n",
        "mcp": "from fastmcp import FastMCP\napp = FastMCP('test')\n@app.tool()\n",
        "python": "from intpot import App\napp = App('test')\n@app.tool()\n",
    }
    source = tmp_path / f"{framework}_app.py"
    source.write_text(
        headers[framework] + "def tool(value: int) -> int:\n    return value + 1\n"
    )
    if framework == "python":
        import importlib.util

        spec = importlib.util.spec_from_file_location("registered_python_app", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema = module.app.schema
    else:
        schema = intpot.load(source).schema
    assert len(schema.tools) == 1
    tool = schema.tools[0]
    assert tool.source_location == (str(source.resolve()), 4, 5)
    assert tool.function_body == "return value + 1"
    if framework == "python":
        assert tool.support_definitions == ()  # No new live-App recovery capability.
