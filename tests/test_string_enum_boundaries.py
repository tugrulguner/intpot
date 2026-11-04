"""Adversarial conformance boundaries for detached string-enum schemas."""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Any

import pytest
from typer.testing import CliRunner

import intpot
from intpot.core.generators.cli import CLIGenerator
from intpot.core.models import ParameterInfo, ParameterSchema, ToolInfo, ToolSchema
from intpot.core.string_enums import StringEnumDefault, StringEnumSpec


@pytest.mark.parametrize(
    "alias",
    [
        "_intpot_enum_\u212a",
        "_intpot_enum_\uff26\uff21\uff33\uff34",
        "_intpot_enum_e\u0301",
    ],
)
def test_enum_import_alias_refuses_identifier_normalization(alias):
    spec = StringEnumSpec("enumapp.modes", "Mode", (("SAFE", "safe"),))
    with pytest.raises(ValueError, match="alias"):
        spec.alias({spec.key: alias})


def test_equal_fresh_enum_capture_preserves_older_identity(enum_package):
    from intpot.core.string_enums import capture_string_enum
    from intpot.runtime import _copy_tool_info

    _, root = enum_package
    owner = __import__(f"{root.name}.modes", fromlist=["Mode"])
    original = owner.Mode
    old = capture_string_enum(original)
    parameter = ParameterInfo(
        "mode", default=StringEnumDefault(old, "SAFE"), string_enum=old
    )
    tool = ToolSchema.from_info(ToolInfo("run", parameters=[parameter]))
    copied = ToolSchema.from_info(_copy_tool_info(tool.to_info()))
    assert copied.parameters[0].string_enum is old
    owner.Mode = Enum(
        "Mode",
        {name: member.value for name, member in original.__members__.items()},
        type=str,
        module=owner.__name__,
    )
    fresh = capture_string_enum(owner.Mode)
    assert fresh == old and hash(fresh) == hash(old)
    assert fresh.to_dict() == old.to_dict()
    assert fresh.resolve() is owner.Mode
    with pytest.raises(TypeError, match="identity changed"):
        old.resolve()
    copied_spec = copied.parameters[0].string_enum
    assert copied_spec is not None
    with pytest.raises(TypeError, match="identity changed"):
        copied_spec.resolve()
    assert fresh.resolve() is owner.Mode


def test_enum_capture_evidence_retains_neither_snapshot_nor_class(enum_package):
    import gc
    import weakref
    from dataclasses import fields

    from intpot.core.string_enums import _CAPTURED_ENUMS, capture_string_enum

    _, root = enum_package
    owner = __import__(f"{root.name}.modes", fromlist=["Mode"])
    spec = capture_string_enum(owner.Mode)
    key = id(spec)
    original = weakref.ref(owner.Mode)
    payload = spec.to_dict()
    decoded = StringEnumSpec.from_dict(json.loads(json.dumps(payload)))
    assert decoded == spec and id(decoded) not in _CAPTURED_ENUMS
    assert [field.name for field in fields(spec)] == [
        "module",
        "name",
        "members",
        "nullable",
    ]
    owner.Mode = Enum(
        "Mode", {"FAST": "fast", "SAFE": "safe"}, type=str, module=owner.__name__
    )
    gc.collect()
    assert original() is None
    with pytest.raises(TypeError, match="identity changed"):
        spec.resolve()
    snapshot = weakref.ref(spec)
    del spec
    gc.collect()
    assert snapshot() is None and key not in _CAPTURED_ENUMS


@pytest.fixture
def enum_package(tmp_path, monkeypatch):
    root = tmp_path / "enum_boundary_pkg"
    root.mkdir()
    (root / "__init__.py").write_text("")
    (root / "modes.py").write_text(
        "from enum import Enum\n"
        "class Mode(str, Enum):\n FAST='fast'\n SAFE='safe'\n"
        "class AliasMode(str, Enum):\n FAST='fast'\n ALSO_FAST='fast'\n"
        "class CustomMissing(str, Enum):\n"
        " FAST='fast'\n"
        " @classmethod\n def _missing_(cls, value): return cls.FAST\n"
        "class CustomInit(str, Enum):\n"
        " def __new__(cls, value):\n  obj=str.__new__(cls,value); obj.extra=1; return obj\n"
        " FAST='fast'\n"
    )
    source = root / "app.py"
    source.write_text(
        "from pathlib import Path\nimport typer\nfrom .modes import Mode\n"
        "app=typer.Typer()\n"
        "@app.command()\n"
        "def run(output: str, mode: Mode = 'safe'):\n"
        " Path(output).write_text(mode.value)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    for key in tuple(sys.modules):
        if key == root.name or key.startswith(root.name + "."):
            del sys.modules[key]
    try:
        yield source, root
    finally:
        for key in tuple(sys.modules):
            if key == root.name or key.startswith(root.name + "."):
                del sys.modules[key]


def test_spec_is_immutable_deep_detached_and_data_only(enum_package, monkeypatch):
    _, root = enum_package
    module = __import__(f"{root.name}.modes", fromlist=["Mode"])
    original = [["FAST", "fast"], ["SAFE", "safe"]]
    spec = StringEnumSpec.from_dict(
        {"module": module.__name__, "name": "Mode", "members": original}
    )
    original[0][0] = "changed"
    assert spec.members == (("FAST", "fast"), ("SAFE", "safe"))
    with pytest.raises((AttributeError, TypeError)):
        spec.name = "Other"
    payload = spec.to_dict()
    monkeypatch.setattr(
        "builtins.__import__",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("imported")),
    )
    restored = StringEnumSpec.from_dict(payload)
    assert restored == spec and hash(restored) == hash(spec)
    payload["members"][0][0] = "mutated"
    assert restored.members[0][0] == "FAST"
    default = StringEnumDefault(spec, "SAFE")
    assert StringEnumDefault.from_dict(default.to_dict()) == default
    param = ParameterInfo("mode", default=default, string_enum=spec)
    schema = ParameterSchema.from_info(param)
    assert hash(schema)
    assert ParameterSchema.from_info(schema.to_info()).to_dict() == schema.to_dict()
    tool = ToolSchema.from_info(ToolInfo("run", parameters=[param]))
    assert json.loads(json.dumps(tool.to_dict())) == tool.to_dict()
    assert ToolSchema.from_info(tool.to_info()).to_dict() == tool.to_dict()
    assert (
        "string_enum" not in ParameterSchema.from_info(ParameterInfo("plain")).to_dict()
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"module": "bad-module.pkg", "name": "Mode", "members": [["A", "a"]]},
        {"module": "pkg.m", "name": "bad-name", "members": [["A", "a"]]},
        {"module": "pkg.m", "name": "Mode", "members": [["bad-name", "a"]]},
        {"module": "pkg.m", "name": "Mode", "members": [["A", 1]]},
        {"module": "pkg.m", "name": "Mode", "members": [["A", "a"], ["A", "b"]]},
        {"module": "pkg.m", "name": "Mode", "members": [["A", "a"], ["B", "a"]]},
        {"module": "pkg.m", "name": "Mode", "members": [["A", "a"]], "nullable": 1},
    ],
)
def test_malformed_specs_are_refused(payload):
    with pytest.raises((TypeError, ValueError)):
        StringEnumSpec.from_dict(payload)


def test_generated_cli_explicit_string_default_and_invalid_value_before_effect(
    enum_package, tmp_path
):
    source, _ = enum_package
    loaded = intpot.load(source)
    effect = tmp_path / "created"
    namespace: dict[str, Any] = {"__name__": "boundary_cli"}
    exec(CLIGenerator().generate(loaded.schema), namespace)
    runner = CliRunner()
    result = runner.invoke(namespace["app"], [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "safe"
    effect.unlink()
    result = runner.invoke(namespace["app"], [str(effect), "--mode", "invalid"])
    assert result.exit_code == 2
    assert not effect.exists()


def test_required_and_nullable_enum_cli_semantics(enum_package):
    source, _ = enum_package
    source.write_text(
        "import typer\nfrom typing import Optional\nfrom .modes import Mode\n"
        "app=typer.Typer()\n@app.command()\n"
        "def run(mode: Mode, maybe: Optional[Mode] = None): typer.echo(str((mode,maybe)))\n"
    )
    loaded = intpot.load(source)
    namespace: dict[str, Any] = {"__name__": "boundary_required"}
    exec(CLIGenerator().generate(loaded.schema), namespace)
    runner = CliRunner()
    assert runner.invoke(namespace["app"], ["fast"]).exit_code == 0
    assert runner.invoke(namespace["app"], []).exit_code == 2
    assert runner.invoke(namespace["app"], ["bad"]).exit_code == 2


@pytest.mark.parametrize(
    "code",
    [
        "from .modes import CustomMissing as Mode",
        "from .modes import CustomInit as Mode",
        "from enum import Enum\nclass Mode(Enum): A='a'",
        "from .modes import AliasMode as Mode",
    ],
)
def test_unsupported_enum_shapes_are_refused_before_loading_or_output(
    enum_package, code, tmp_path
):
    source, root = enum_package
    source.write_text(
        "from pathlib import Path\nimport typer\n"
        + code
        + "\napp=typer.Typer()\n@app.command()\ndef run(output: str, mode: Mode): Path(output).write_text(str(mode))\n"
    )
    output = tmp_path / "must-not-exist"
    try:
        loaded = intpot.load(source)
        CLIGenerator().generate(loaded.schema)
    except (TypeError, ValueError, ImportError, RuntimeError):
        assert not output.exists()
    else:
        pytest.fail(f"unsupported enum form accepted: {code}")


def test_stale_enum_export_rejected_before_scaffold_callback(
    enum_package, monkeypatch, tmp_path
):
    source, root = enum_package
    loaded = intpot.load(source)
    _ = loaded.schema
    module = sys.modules[f"{root.name}.modes"]
    module.Mode = Enum("Mode", {"FAST": "different"}, type=str)
    called = False

    def callback(*args, **kwargs):
        nonlocal called
        called = True

    with pytest.raises((TypeError, ValueError, RuntimeError)):
        loaded.write(tmp_path / "stale.py", "api", allow_scaffold=True)
    assert not called


def test_alias_and_private_name_collisions_keep_enum_import_valid(
    enum_package, tmp_path
):
    source, _ = enum_package
    source.write_text(
        "from pathlib import Path\nimport typer\nfrom .modes import Mode as _intpot_enum_Mode\n"
        "app=typer.Typer()\n@app.command()\n"
        "def run(output: str, _intpot_enum_Mode: str, mode: _intpot_enum_Mode):\n"
        " Path(output).write_text(mode.value)\n"
    )
    loaded = intpot.load(source)
    generated = CLIGenerator().generate(loaded.schema)
    namespace: dict[str, Any] = {"__name__": "collision_generated"}
    exec(compile(generated, "generated.py", "exec"), namespace)
    effect = tmp_path / "collision"
    result = CliRunner().invoke(namespace["app"], [str(effect), "occupied", "fast"])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "fast"
