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


def test_nested_enum_collection_does_not_become_unchecked_scalar(enum_source):
    enum_source.write_text(
        enum_source.read_text().replace(
            "mode: Mode = Mode.SAFE", "mode: list[list[Mode]] = []"
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


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_registered_fallback_preserves_enum_case_refusal(
    enum_source, tmp_path, monkeypatch, target
):
    enum_source.write_text(
        enum_source.read_text().replace(
            "mode: Mode = Mode.SAFE",
            "mode: Mode = typer.Option(Mode.SAFE, case_sensitive=False)",
        )
    )
    _, original = detect_source(enum_source)
    effect = tmp_path / "native-case"
    result = CliRunner().invoke(original, [str(effect), "--mode", "FAST"])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "fast"

    def fail_tree():
        raise RuntimeError("force registered-command fallback")

    monkeypatch.setattr(original, "_get_command", fail_tree, raising=False)
    destination = tmp_path / f"fallback-{target}.py"
    with pytest.raises(TypeError, match="case-insensitive"):
        intpot.load(enum_source).write(destination, target, allow_scaffold=True)
    assert not destination.exists()


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("override", ["click_type", "parser"])
def test_enum_custom_choices_refuse_before_writes(
    enum_source, tmp_path, monkeypatch, target, fallback, annotated, scaffold, override
):
    enum_source.with_name("modes.py").write_text(
        "from enum import StrEnum\nclass Mode(StrEnum):\n FAST='fast'\n SAFE='safe'\n"
    )
    selection = "_Choice(['safe'])" if override == "click_type" else "_only_safe"
    declaration = (
        f"mode: Annotated[Mode, typer.Option({override}={selection})] = Mode.SAFE"
        if annotated
        else f"mode: Mode = typer.Option(Mode.SAFE, {override}={selection})"
    )
    enum_source.write_text(
        "from pathlib import Path\nfrom typing import Annotated\nimport typer\n"
        "from typer.main import get_click_type\nfrom typer.models import OptionInfo\n"
        "from .modes import Mode\n"
        "_Choice = type(get_click_type(annotation=Mode, parameter_info=OptionInfo()))\n"
        "def _only_safe(value):\n"
        "    if value != 'safe':\n        raise ValueError('Only safe is allowed')\n"
        "    return Mode.SAFE\n"
        "app = typer.Typer()\n@app.command()\n"
        f"def run(output: str, {declaration}):\n"
        "    Path(output).write_text(str(mode))\n    typer.echo(str(mode))\n"
    )
    _, original = detect_source(enum_source)
    effect = tmp_path / "native-restricted-choice"
    runner = CliRunner()
    for arguments in ([], ["--mode", "safe"]):
        accepted = runner.invoke(original, [str(effect), *arguments])
        assert accepted.exit_code == 0, accepted.exception
        assert effect.read_text() == "safe"
        effect.unlink()
    assert runner.invoke(original, [str(effect), "--mode", "fast"]).exit_code == 2
    assert not effect.exists()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(original, "_get_command", fail_tree, raising=False)
    destination = tmp_path / f"restricted-{target}.py"
    with pytest.raises(TypeError, match=r"Custom.*enum"):
        intpot.load(enum_source).write(destination, target, allow_scaffold=scaffold)
    assert not destination.exists()
    assert not effect.exists()


@pytest.mark.parametrize("occupied_alias", [False, True])
@pytest.mark.parametrize("fallback", [False, True])
def test_nullable_enum_preserves_optional_helper_bindings(
    enum_source, tmp_path, occupied_alias, fallback, monkeypatch
):
    helpers = "def Optional(mode):\n    return 'none' if mode is None else mode.value\n"
    if occupied_alias:
        helpers += "def _intpot_typing_Optional():\n    return '!'\n"
    enum_source.with_name("helpers.py").write_text(helpers)
    helper_names = "Optional, _intpot_typing_Optional" if occupied_alias else "Optional"
    suffix = " + _intpot_typing_Optional()" if occupied_alias else ""
    enum_source.write_text(
        "from pathlib import Path\nfrom typing import Optional as Maybe\nimport typer\n"
        f"from .helpers import {helper_names}\n"
        "from .modes import Mode\napp = typer.Typer()\n@app.command()\n"
        "def run(output: str, mode: Maybe[Mode] = None):\n"
        f"    value = Optional(mode){suffix}\n"
        "    Path(output).write_text(value)\n    typer.echo(value)\n"
    )
    _, native = detect_source(enum_source)
    effect = tmp_path / "optional-helper-effect"
    expected_suffix = "!" if occupied_alias else ""
    for arguments, expected in (([], "none"), (["--mode", "fast"], "fast")):
        result = CliRunner().invoke(native, [str(effect), *arguments])
        assert result.exit_code == 0, result.exception
        assert effect.read_text() == expected + expected_suffix
        effect.unlink()
    assert CliRunner().invoke(native, [str(effect), "--mode", "invalid"]).exit_code == 2
    assert not effect.exists()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    loaded = intpot.load(enum_source)
    cli: dict[str, Any] = {"__name__": "nullable_collision_cli"}
    exec(CLIGenerator().generate(loaded.schema), cli)
    for arguments, expected in (([], "none"), (["--mode", "fast"], "fast")):
        result = CliRunner().invoke(cli["app"], [str(effect), *arguments])
        assert result.exit_code == 0, result.exception
        assert effect.read_text() == expected + expected_suffix
        effect.unlink()
    assert (
        CliRunner().invoke(cli["app"], [str(effect), "--mode", "invalid"]).exit_code
        == 2
    )
    assert not effect.exists()
    api: dict[str, Any] = {"__name__": "nullable_collision_api"}
    exec(loaded.to_api(), api)
    with TestClient(api["app"]) as client:
        for extra, expected in (
            ({}, "none"),
            ({"mode": None}, "none"),
            ({"mode": "fast"}, "fast"),
        ):
            result = client.post("/run", json={"output": str(effect), **extra})
            assert result.status_code == 200, result.text
            assert result.json() == {"result": expected + expected_suffix}
            assert effect.read_text() == expected + expected_suffix
            effect.unlink()
        assert (
            client.post(
                "/run", json={"output": str(effect), "mode": "invalid"}
            ).status_code
            == 422
        )
        assert not effect.exists()
    mcp: dict[str, Any] = {"__name__": "nullable_collision_mcp"}
    exec(loaded.to_mcp(), mcp)

    async def check_mcp():
        async with Client(mcp["mcp"]) as client:
            for extra, expected in (
                ({}, "none"),
                ({"mode": None}, "none"),
                ({"mode": "fast"}, "fast"),
            ):
                result = await client.call_tool("run", {"output": str(effect), **extra})
                assert result.content[0].text == expected + expected_suffix
                assert effect.read_text() == expected + expected_suffix
                effect.unlink()
            result = await client.call_tool(
                "run", {"output": str(effect), "mode": "invalid"}, raise_on_error=False
            )
            assert result.is_error
            assert not effect.exists()

    asyncio.run(check_mcp())


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("scaffold", [False, True])
def test_enum_default_factories_refuse_without_execution(
    enum_source, tmp_path, monkeypatch, target, fallback, annotated, scaffold
):
    declaration = (
        "mode: Annotated[Maybe[Mode], typer.Option(default_factory=choose)]"
        if annotated
        else "mode: Maybe[Mode] = typer.Option(default_factory=choose)"
    )
    enum_source.write_text(
        "from pathlib import Path\nfrom typing import Optional as Maybe, Annotated\nimport typer\n"
        "from .modes import Mode\ncalls = []\n"
        "def choose():\n    calls.append('factory')\n    return Mode.FAST\n"
        "app = typer.Typer()\n@app.command()\n"
        f"def run(output: str, {declaration}):\n"
        "    Path(output).write_text(mode.value)\n    typer.echo(mode.value)\n"
    )
    _, native = detect_source(enum_source)
    module = sys.modules["enumapp.main"]
    assert module.calls == []
    effect = tmp_path / "factory-effect"
    result = CliRunner().invoke(native, [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "fast" and module.calls == ["factory"]
    effect.unlink()
    explicit = CliRunner().invoke(native, [str(effect), "--mode", "safe"])
    assert explicit.exit_code == 0, explicit.exception
    assert effect.read_text() == "safe" and module.calls == ["factory"]
    effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / f"factory-{target}.py"
    with pytest.raises(TypeError):
        intpot.load(enum_source).write(destination, target, allow_scaffold=scaffold)
    assert not destination.exists() and not effect.exists()
    assert module.calls == ["factory"]


@pytest.mark.parametrize("fallback", [False, True])
def test_enum_member_names_are_not_option_metadata(
    enum_source, tmp_path, monkeypatch, fallback
):
    enum_source.with_name("modes.py").write_text(
        "from enum import Enum\nclass Mode(str, Enum):\n"
        " SAFE='safe'\n FAST='fast'\n default_factory='factory member'\n"
        " parser='parser member'\n click_type='click member'\n case_sensitive=''\n"
        " default='wrong default member'\n help='member help'\n envvar='environment member'\n"
        " prompt='prompt member'\n"
    )
    _, native = detect_source(enum_source)
    effect = tmp_path / "metadata-member-effect"
    result = CliRunner().invoke(native, [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "safe"
    effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    namespace: dict[str, Any] = {"__name__": "metadata_members_api"}
    exec(intpot.load(enum_source).to_api(), namespace)
    with TestClient(namespace["app"]) as client:
        result = client.post("/run", json={"output": str(effect)})
        assert result.status_code == 200, result.text
        assert effect.read_text() == "safe"


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("environment", [None, "fast", "invalid"])
@pytest.mark.parametrize(
    "names", ["INTPOT_REVIEW_MODE", ["INTPOT_REVIEW_MISSING", "INTPOT_REVIEW_MODE"]]
)
def test_enum_environment_defaults_refuse_before_writes(
    enum_source,
    tmp_path,
    monkeypatch,
    target,
    fallback,
    annotated,
    scaffold,
    environment,
    names,
):
    monkeypatch.delenv("INTPOT_REVIEW_MISSING", raising=False)
    if environment is None:
        monkeypatch.delenv("INTPOT_REVIEW_MODE", raising=False)
    else:
        monkeypatch.setenv("INTPOT_REVIEW_MODE", environment)
    declaration = (
        f"mode: Annotated[Mode, typer.Option(envvar={names!r})] = Mode.SAFE"
        if annotated
        else f"mode: Mode = typer.Option(Mode.SAFE, envvar={names!r})"
    )
    enum_source.write_text(
        "from pathlib import Path\nfrom typing import Annotated\nimport typer\n"
        "from .modes import Mode\napp = typer.Typer()\n@app.command()\n"
        f"def run(output: str, {declaration}):\n"
        "    Path(output).write_text(mode.value)\n    typer.echo(mode.value)\n"
    )
    _, native = detect_source(enum_source)
    effect = tmp_path / "environment-effect"
    result = CliRunner().invoke(native, [str(effect)])
    if environment == "invalid":
        assert result.exit_code == 2 and not effect.exists()
    else:
        assert result.exit_code == 0, result.exception
        assert effect.read_text() == (environment or "safe")
        effect.unlink()
    explicit = CliRunner().invoke(native, [str(effect), "--mode", "safe"])
    assert explicit.exit_code == 0, explicit.exception
    assert effect.read_text() == "safe"
    effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / f"environment-{target}.py"
    with pytest.raises(TypeError, match=r"Environment.*enum"):
        intpot.load(enum_source).write(destination, target, allow_scaffold=scaffold)
    assert not destination.exists() and not effect.exists()


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("collision", [False, True])
@pytest.mark.parametrize("kind", ["member", "type", "module"])
def test_enum_normalized_identifiers_refuse_before_writes(
    enum_source, tmp_path, monkeypatch, target, fallback, scaffold, collision, kind
):
    enum_source.with_name("modes.py").write_text(
        "from enum import Enum\n"
        + (
            "Mode=Enum('Mode', {'\u212aEY':'safe'"
            + (",'KEY':'fast'" if collision else ",'OTHER':'fast'")
            + "},type=str,module=__name__)\n"
            if kind == "member"
            else "Mode=Enum('\u212aind', {'SAFE':'safe','FAST':'fast'},type=str,module=__name__)\nglobals()['\u212aind']=Mode\n"
            + (
                "Kind=Enum('Kind', {'SAFE':'fast','FAST':'safe'},type=str,module=__name__)\n"
                if collision
                else ""
            )
            if kind == "type"
            else "Mode=Enum('Mode', {'SAFE':'safe','FAST':'fast'},type=str,module=__name__)\n"
        )
    )
    if kind == "module":
        enum_source.with_name("\uff26\uff21\uff33\uff34.py").write_text(
            enum_source.with_name("modes.py").read_text()
        )
        if collision:
            enum_source.with_name("FAST.py").write_text(
                "from enum import Enum\nMode=Enum('Mode', {'SAFE':'fast','FAST':'safe'},type=str,module=__name__)\n"
            )
        source_import = "from importlib import import_module\nMode=import_module('.\uff26\uff21\uff33\uff34',__package__).Mode\n"
    else:
        source_import = "from .modes import Mode\n"
    member = "\u212aEY" if kind == "member" else "SAFE"
    enum_source.write_text(
        "from pathlib import Path\nimport typer\n"
        + source_import
        + "app=typer.Typer()\n@app.command()\n"
        + f"def run(output:str,mode:Mode=Mode[{member!r}]):\n"
        + "    Path(output).write_text(mode.value)\n    typer.echo(mode.value)\n"
    )
    _, native = detect_source(enum_source)
    effect = tmp_path / "normalization-effect"
    result = CliRunner().invoke(native, [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "safe"
    effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / f"normalization-{target}.py"
    with pytest.raises((TypeError, ValueError), match="string-enum"):
        intpot.load(enum_source).write(destination, target, allow_scaffold=scaffold)
    assert not destination.exists() and not effect.exists()


@pytest.mark.parametrize("fallback", [False, True])
def test_stable_unicode_enum_bindings_preserve_native_effects(
    enum_source, tmp_path, monkeypatch, fallback
):
    enum_source.with_name("ΔΟΚΙΜΗ.py").write_text(
        "from enum import Enum\nMode=Enum('ΔΕΛΤΑ', {'ΑΣΦΑΛΕΣ':'safe','ΓΡΗΓΟΡΟ':'fast'},type=str,module=__name__)\n"
        "globals()['ΔΕΛΤΑ']=Mode\n"
    )
    enum_source.write_text(
        "from pathlib import Path\nimport typer\nfrom .ΔΟΚΙΜΗ import Mode\n"
        "def _intpot_enum_ΔΕΛΤΑ():\n    return '!'\n"
        "app=typer.Typer()\n@app.command()\n"
        "def run(output:str,mode:Mode=Mode['ΑΣΦΑΛΕΣ']):\n"
        "    value=mode.value+_intpot_enum_ΔΕΛΤΑ()\n"
        "    Path(output).write_text(value)\n    typer.echo(value)\n"
    )
    _, native = detect_source(enum_source)
    effect = tmp_path / "unicode-effect"
    result = CliRunner().invoke(native, [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "safe!"
    effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    loaded = intpot.load(enum_source)
    namespace: dict[str, Any] = {"__name__": "stable_unicode_cli"}
    exec(CLIGenerator().generate(loaded.schema), namespace)
    result = CliRunner().invoke(namespace["app"], [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "safe!"
    effect.unlink()
    namespace = {"__name__": "stable_unicode_api"}
    exec(loaded.to_api(), namespace)
    with TestClient(namespace["app"]) as client:
        for extra, expected in (({}, "safe!"), ({"mode": "fast"}, "fast!")):
            response = client.post("/run", json={"output": str(effect), **extra})
            assert response.status_code == 200, response.text
            assert effect.read_text() == expected
            effect.unlink()
        assert (
            client.post(
                "/run", json={"output": str(effect), "mode": "invalid"}
            ).status_code
            == 422
        )
        assert not effect.exists()
    namespace = {"__name__": "stable_unicode_mcp"}
    exec(loaded.to_mcp(), namespace)

    async def check():
        async with Client(namespace["mcp"]) as client:
            for extra, expected in (({}, "safe!"), ({"mode": "fast"}, "fast!")):
                response = await client.call_tool(
                    "run", {"output": str(effect), **extra}
                )
                assert response.content[0].text == expected
                assert effect.read_text() == expected
                effect.unlink()

    asyncio.run(check())


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("default", ["Mode.SAFE", "'safe'"])
def test_identical_enum_replacement_refuses_before_writes(
    enum_source, tmp_path, monkeypatch, target, fallback, scaffold, default
):
    from enum import Enum

    enum_source.with_name("helpers.py").write_text(
        "from .modes import Mode as OriginalMode\ndef matches(mode):\n    return type(mode) is OriginalMode\n"
    )
    enum_source.write_text(
        "from pathlib import Path\nimport typer\nfrom .modes import Mode\nfrom .helpers import matches\n"
        "app=typer.Typer()\n@app.command()\n"
        f"def run(output:str,mode:Mode={default}):\n"
        "    value=str(matches(mode))\n    Path(output).write_text(value)\n    typer.echo(value)\n"
    )
    _, native = detect_source(enum_source)
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    loaded = intpot.load(enum_source)
    schema = loaded.schema
    if fallback:
        monkeypatch.delattr(native, "_get_command")
    namespace: dict[str, Any] = {"__name__": "unchanged_enum_api"}
    exec(loaded.to_api(), namespace)
    effect = tmp_path / "identity-effect"
    with TestClient(namespace["app"]) as client:
        response = client.post("/run", json={"output": str(effect)})
        assert response.status_code == 200, response.text
        assert effect.read_text() == "True"
        effect.unlink()
    owner = sys.modules["enumapp.modes"]
    original = owner.Mode
    owner.Mode = Enum(
        "Mode",
        {name: member.value for name, member in original.__members__.items()},
        type=str,
        module=owner.__name__,
    )
    assert owner.Mode is not original
    result = CliRunner().invoke(native, [str(effect)])
    assert result.exit_code == 0, result.exception
    assert effect.read_text() == "True"
    effect.unlink()
    assert loaded.schema is schema
    destination = tmp_path / f"identical-{target}.py"
    with pytest.raises(TypeError, match="changed since inspection"):
        loaded.write(destination, target, allow_scaffold=scaffold)
    assert not destination.exists() and not effect.exists()


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
