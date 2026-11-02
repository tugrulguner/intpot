"""Native file effects and conversion of ordinary importable string enums."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from typer.testing import CliRunner

import intpot
from intpot.core.detector import detect_source
from intpot.core.generators.cli import CLIGenerator


@pytest.fixture
def enum_source(tmp_path, monkeypatch):
    before = {
        k: v
        for k, v in sys.modules.items()
        if k == "enumapp" or k.startswith("enumapp.")
    }
    for key in before:
        del sys.modules[key]
    package = tmp_path / "enumapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "modes.py").write_text(
        "from enum import Enum\nclass Mode(str, Enum):\n    FAST = 'fast'\n    SAFE = 'safe'\n"
    )
    source = package / "main.py"
    source.write_text(
        "from pathlib import Path\nimport typer\nfrom .modes import Mode\napp = typer.Typer()\n@app.command()\ndef run(output: str, mode: Mode = Mode.SAFE):\n    Path(output).write_text(mode.value)\n    typer.echo(mode.value)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        yield source
    finally:
        for key in tuple(sys.modules):
            if key == "enumapp" or key.startswith("enumapp."):
                del sys.modules[key]
        sys.modules.update(before)


def test_enum_collection_does_not_become_unchecked_scalar(enum_source):
    enum_source.write_text(
        enum_source.read_text().replace(
            "mode: Mode = Mode.SAFE", "mode: list[Mode] = []"
        )
    )
    with pytest.raises(TypeError, match="enum"):
        intpot.load(enum_source).to_api()


def test_enum_spec_rejects_nontext_module():
    from intpot.core.string_enums import StringEnumSpec

    with pytest.raises((TypeError, ValueError)):
        StringEnumSpec.from_dict(
            {"module": 123, "name": "Mode", "members": [["A", "a"]]}
        )


def test_enum_owner_must_have_matching_import_spec(enum_source, monkeypatch):
    from intpot.core.string_enums import capture_string_enum

    _ = intpot.load(enum_source).schema
    owner = sys.modules["enumapp.modes"]
    monkeypatch.setattr(owner.__spec__, "name", "not.the.owner")
    with pytest.raises(TypeError):
        capture_string_enum(owner.Mode)


def test_enum_capture_does_not_invoke_custom_value_property(enum_source):
    from intpot.core.string_enums import capture_string_enum

    modes = enum_source.with_name("modes.py")
    modes.write_text(
        modes.read_text()
        + "    @property\n    def value(self):\n        raise AssertionError('custom property executed')\n"
    )
    detect_source(enum_source)
    with pytest.raises(TypeError):
        capture_string_enum(vars(sys.modules["enumapp.modes"])["Mode"])


def test_stdlib_strenum_default_reaches_native_http_body(enum_source, tmp_path):
    enum_source.with_name("modes.py").write_text(
        "from enum import StrEnum\nclass Mode(StrEnum):\n FAST='fast'\n SAFE='safe'\n"
    )
    namespace: dict[str, Any] = {"__name__": "strenum_api"}
    exec(intpot.load(enum_source).to_api(), namespace)
    effect = tmp_path / "strenum"
    with TestClient(namespace["app"]) as client:
        response = client.post("/run", json={"output": str(effect)})
        assert response.status_code == 200, response.text
        assert effect.read_text() == "safe"
        effect.unlink()
        assert (
            client.post(
                "/run", json={"output": str(effect), "mode": "invalid"}
            ).status_code
            == 422
        )
        assert not effect.exists()


def test_postponed_enum_annotation(enum_source):
    enum_source.write_text(
        "from __future__ import annotations\n" + enum_source.read_text()
    )
    loaded = intpot.load(enum_source)
    assert loaded.schema.tools[0].parameters[1].string_enum is not None


def test_enum_metadata_runtime_copy(enum_source):
    from intpot.runtime import _copy_tool_info

    tool = intpot.load(enum_source).tools[0]
    assert (
        _copy_tool_info(tool).parameters[1].string_enum
        == tool.parameters[1].string_enum
    )


def test_enum_schema_rejects_mismatched_default(enum_source):
    from dataclasses import replace

    loaded = intpot.load(enum_source)
    parameter = loaded.schema.tools[0].parameters[1]
    with pytest.raises((TypeError, ValueError)):
        replace(parameter, default="invalid")
    with pytest.raises((TypeError, ValueError)):
        replace(parameter, string_enum={"name": "mutable"})


def test_string_enum_native_and_generated_file_effects(enum_source, tmp_path):
    _, native = detect_source(enum_source)
    runner = CliRunner()
    effect = tmp_path / "effect"
    for arguments, expected in (([], "safe"), (["--mode", "fast"], "fast")):
        result = runner.invoke(native, [str(effect), *arguments])
        assert result.exit_code == 0, result.exception
        assert effect.read_text() == expected
        effect.unlink()
    assert runner.invoke(native, [str(effect), "--mode", "invalid"]).exit_code == 2
    assert not effect.exists()

    loaded = intpot.load(enum_source)
    namespace: dict[str, Any] = {"__name__": "enum_generated_cli"}
    exec(CLIGenerator().generate(loaded.schema), namespace)
    for arguments, expected in (([], "safe"), (["--mode", "fast"], "fast")):
        result = runner.invoke(namespace["app"], [str(effect), *arguments])
        assert result.exit_code == 0, result.exception
        assert effect.read_text() == expected
        effect.unlink()
    assert (
        runner.invoke(namespace["app"], [str(effect), "--mode", "invalid"]).exit_code
        == 2
    )
    assert not effect.exists()

    api: dict[str, Any] = {"__name__": "enum_generated_api"}
    exec(loaded.to_api(), api)
    with TestClient(api["app"]) as client:
        for extra, expected in (({}, "safe"), ({"mode": "fast"}, "fast")):
            response = client.post("/run", json={"output": str(effect), **extra})
            assert response.status_code == 200, response.text
            assert response.json() == {"result": expected}
            assert effect.read_text() == expected
            effect.unlink()
        assert (
            client.post(
                "/run", json={"output": str(effect), "mode": "invalid"}
            ).status_code
            == 422
        )
        assert not effect.exists()

    mcp: dict[str, Any] = {"__name__": "enum_generated_mcp"}
    exec(loaded.to_mcp(), mcp)

    async def call():
        async with Client(mcp["mcp"]) as client:
            for extra, expected in (({}, "safe"), ({"mode": "fast"}, "fast")):
                result = await client.call_tool("run", {"output": str(effect), **extra})
                assert result.content[0].text == expected
                assert effect.read_text() == expected
                effect.unlink()
            result = await client.call_tool(
                "run", {"output": str(effect), "mode": "invalid"}, raise_on_error=False
            )
            assert result.is_error
            assert not effect.exists()

    asyncio.run(call())
