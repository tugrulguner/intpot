from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from intpot.core.models import ToolInfo, ToolSchema
from intpot.core.provenance import callable_source_metadata, inspected_callable_metadata


def _load(path):
    spec = importlib.util.spec_from_file_location("digest_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verified_callable_metadata_includes_digest_of_exact_file_text(tmp_path):
    path = tmp_path / "source.py"
    text = "def tool():\n    return 7\n"
    path.write_text(text, encoding="utf-8")
    metadata = callable_source_metadata(_load(path).tool)
    assert metadata["source_location"] == (str(path.resolve()), 1, 2)
    assert metadata["source_digest"] == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_dynamic_and_stale_callables_have_no_digest(tmp_path):
    namespace: dict[str, Any] = {}
    exec("def dynamic(): return 1", namespace)
    assert callable_source_metadata(namespace["dynamic"]) == {
        "source_location": None,
        "source_digest": None,
    }
    path = tmp_path / "stale.py"
    path.write_text("def tool():\n    return 1\n", encoding="utf-8")
    fn = _load(path).tool
    path.write_text("def tool():\n    return 2\n", encoding="utf-8")
    assert callable_source_metadata(fn)["source_digest"] is None


def test_inspected_plain_helper_digest_is_limited_to_existing_recovery(tmp_path):
    path = tmp_path / "helpers.py"
    path.write_text(
        "def plain(x):\n    return x + 1\ndef tool(x):\n    return plain(x)\n",
        encoding="utf-8",
    )
    metadata = inspected_callable_metadata(_load(path).tool)
    assert metadata["support_source_digests"] == {
        "plain": hashlib.sha256(path.read_bytes()).hexdigest()
    }
    assert metadata["source_digest"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_schema_detaches_digests_validates_and_roundtrips():
    support = {"helper": "a" * 64}
    info = ToolInfo("tool", source_digest="b" * 64, support_source_digests=support)
    schema = ToolSchema.from_info(info)
    support["helper"] = "c" * 64
    assert schema.support_source_digests == (("helper", "a" * 64),)
    assert hash(schema) == hash(ToolSchema.from_info(schema.to_info()))
    detached = schema.to_info()
    detached.support_source_digests["helper"] = "d" * 64
    assert schema.support_source_digests == (("helper", "a" * 64),)
    assert json.loads(json.dumps(schema.to_dict()))["source_digest"] == "b" * 64
    assert schema.to_dict()["support_source_digests"] == {"helper": "a" * 64}
    with pytest.raises(FrozenInstanceError):
        cast(Any, schema).source_digest = None


@pytest.mark.parametrize("digest", ["A" * 64, "f" * 63, "z" * 64, "f" * 65])
def test_schema_rejects_invalid_digest(digest):
    with pytest.raises(ValueError, match="digest"):
        ToolSchema("tool", source_digest=digest)


@pytest.mark.parametrize(
    ("framework", "header"),
    [
        ("cli", "import typer\napp = typer.Typer()\n@app.command()\n"),
        ("mcp", "from fastmcp import FastMCP\napp = FastMCP('test')\n@app.tool()\n"),
        ("python", "from intpot import App\napp = App('test')\n@app.tool()\n"),
    ],
)
def test_inspector_paths_forward_callable_digest(tmp_path, framework, header):
    import intpot

    path = tmp_path / f"{framework}.py"
    text = header + "def tool(value: int) -> int:\n    return value + 1\n"
    path.write_text(text, encoding="utf-8")
    if framework == "python":
        tool = _load(path).app.schema.tools[0]
    else:
        tool = intpot.load(path).schema.tools[0]
    assert tool.source_digest == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_runtime_registration_captures_tool_digest_without_helpers(tmp_path):
    path = tmp_path / "runtime_fixture.py"
    text = (
        "from intpot import App\napp = App()\n@app.tool()\ndef tool():\n    return 3\n"
    )
    path.write_text(text, encoding="utf-8")
    module = _load(path)
    schema = module.app.schema.tools[0]
    assert schema.source_digest == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert schema.support_source_digests == ()
    copied = module.app._tools[0].info
    assert copied.source_digest == schema.source_digest


def test_runtime_projection_forwards_digests():
    from intpot.runtime import _copy_tool_info

    info = ToolInfo(
        "tool", source_digest="e" * 64, support_source_digests={"h": "f" * 64}
    )
    projected = _copy_tool_info(info)
    assert projected.source_digest == info.source_digest
    assert projected.support_source_digests == info.support_source_digests
