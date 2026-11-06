"""Native-controlled repeatable enum options, not full Docling conversion."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError
from typer.testing import CliRunner

import intpot
from intpot.core.detector import detect_source
from intpot.core.generators.cli import CLIGenerator


def test_collection_metadata_rejects_scalar_member_default():
    from intpot.core.models import ParameterInfo, ParameterSchema
    from intpot.core.string_enums import StringEnumDefault, StringEnumSpec

    spec = StringEnumSpec(
        "enum_collection_app.modes", "Mode", (("MD", "md"),), many=True
    )
    with pytest.raises(TypeError, match="Enum default"):
        ParameterSchema.from_info(
            ParameterInfo(
                "modes", default=StringEnumDefault(spec, "MD"), string_enum=spec
            )
        )


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "declaration",
    [
        "modes:list[Mode]",
        "modes:list[Mode]=typer.Option(...,'--to')",
        "modes:list[Mode]=typer.Argument(None)",
        "modes:tuple[Mode,...]=typer.Option(None,'--to')",
        "modes:list[list[Mode]]=typer.Option(None,'--to')",
        "modes:list[Mode | None]=typer.Option(None,'--to')",
    ],
)
@pytest.mark.parametrize("target", ["api", "mcp"])
def test_unsupported_collection_shapes_refuse_before_scaffolds(
    collection_source, tmp_path, monkeypatch, fallback, declaration, target
):
    collection_source.write_text(
        collection_source.read_text().replace(
            "modes:list[Mode]=typer.Option(None,'--to')", declaration
        )
    )
    _, native = detect_source(collection_source)
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "unsupported.py"
    with pytest.raises((TypeError, ValueError), match="enum"):
        intpot.load(collection_source).write(destination, target, allow_scaffold=True)
    assert not destination.exists()


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "setting",
    [
        "case_sensitive=False",
        "envvar='INTPOT_COLLECTION_MODES'",
        "parser=lambda value: value",
        "callback=lambda value: value",
        "default_factory=lambda: []",
    ],
)
@pytest.mark.parametrize("target", ["api", "mcp"])
def test_collection_metadata_guards_survive_fallback(
    collection_source, tmp_path, monkeypatch, fallback, setting, target
):
    collection_source.write_text(
        collection_source.read_text().replace(
            "typer.Option(None,'--to')", f"typer.Option(None,'--to',{setting})"
        )
    )
    _, native = detect_source(collection_source)
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "guarded.py"
    with pytest.raises((TypeError, intpot.UnsupportedCLIParameterCallbackError)):
        intpot.load(collection_source).write(destination, target, allow_scaffold=True)
    assert not destination.exists()


def test_collection_metadata_is_detached_and_preserves_live_origin(
    collection_source, monkeypatch
):
    from enum import Enum

    from intpot.core.string_enums import StringEnumSpec
    from intpot.runtime import _copy_tool_info

    loaded = intpot.load(collection_source)
    tool = loaded.schema.tools[0]
    parameter = next(p for p in tool.parameters if p.name == "modes")
    spec = parameter.string_enum
    assert spec is not None and spec.many and not spec.nullable
    payload = spec.to_dict()
    assert payload["many"] is True
    scalar = StringEnumSpec(spec.module, spec.name, spec.members)
    assert "many" not in scalar.to_dict() and scalar != spec
    assert hash(parameter)
    copied = _copy_tool_info(tool.to_info())
    assert copied.parameters[-1].string_enum is spec
    with monkeypatch.context() as isolated:
        isolated.setattr(
            "builtins.__import__",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("imported")),
        )
        assert StringEnumSpec.from_dict(payload) == spec
    owner = sys.modules[spec.module]
    owner.Mode = Enum("Mode", dict(spec.members), type=str, module=spec.module)
    with pytest.raises(TypeError, match="identity changed"):
        spec.resolve()
    # Schema hashing and data serialization do not resolve or retain live classes.
    assert (
        loaded.schema.to_dict()["tools"][0]["parameters"][-1]["string_enum"]["many"]
        is True
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_collection_omission_uses_only_builtin_empty_converter(
    collection_source, monkeypatch, legacy
):
    import typer.main

    from intpot.core.inspectors.cli import _enum_parameter_default

    parameter = intpot.load(collection_source).schema.tools[0].parameters[-1]
    assert parameter.string_enum is not None
    calls = []

    def old_factory(convertor):
        assert convertor is None

        def convert(value):
            calls.append(value)
            return list(value)

        return convert

    def new_factory(convertor, default_value):
        assert convertor is None and default_value is None

        def convert(value):
            calls.append(value)
            return None

        return convert

    monkeypatch.setattr(
        typer.main, "generate_list_convertor", old_factory if legacy else new_factory
    )
    result = _enum_parameter_default(parameter.string_enum, None)
    assert result == ([] if legacy else None)
    assert calls == [()]


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("nullable", [False, True])
@pytest.mark.parametrize("private_collision", [False, True])
def test_collection_preserves_list_helper_bindings(
    collection_source, tmp_path, monkeypatch, fallback, nullable, private_collision
):
    support = "def list(values):\n"
    if private_collision:
        support = "def _intpot_defaults_builtins():\n return 'original'\n" + support
        support += " assert _intpot_defaults_builtins() == 'original'\n"
    support += " return None if values is None else [item.value for item in values]\n"
    text = collection_source.read_text().replace(
        "import typer\n", "import typer\nfrom typing import List as Modes\n"
    )
    text = text.replace("app=typer.Typer()\n", "app=typer.Typer()\n" + support)
    text = text.replace("modes:list[Mode]", "modes:Modes[Mode]")
    text = text.replace(
        "value=None if modes is None else [m.value for m in modes]", "value=list(modes)"
    )
    collection_source.write_text(text)
    test_collection_consumers_preserve_none_order_duplicates(
        collection_source, tmp_path, monkeypatch, fallback, nullable, "None"
    )


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("scalar", [False, True])
@pytest.mark.parametrize("prompt", [True, "Choose formats", ""])
@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("scaffold", [False, True])
def test_prompt_backed_enums_refuse_before_writes(
    collection_source,
    tmp_path,
    monkeypatch,
    fallback,
    annotated,
    scalar,
    prompt,
    target,
    scaffold,
):
    annotation = "Optional[Mode]" if scalar else "list[Mode]"
    if annotated:
        declaration = (
            f"modes:Annotated[{annotation},typer.Option('--to',prompt={prompt!r})]=None"
        )
    else:
        declaration = f"modes:{annotation}=typer.Option(None,'--to',prompt={prompt!r})"
    text = collection_source.read_text().replace(
        "import typer\n", "import typer\nfrom typing import Annotated,Optional\n"
    )
    text = text.replace("modes:list[Mode]=typer.Option(None,'--to')", declaration)
    if scalar:
        text = text.replace("[m.value for m in modes]", "modes.value")
    collection_source.write_text(text)
    _, native = detect_source(collection_source)
    effect = tmp_path / "prompt-effect.json"
    result = CliRunner().invoke(native, [str(effect), "--to", "md"])
    assert result.exit_code == 0, result.exception
    assert json.loads(effect.read_text()) == ("md" if scalar else ["md"])
    effect.unlink()
    if scalar:
        result = CliRunner().invoke(native, [str(effect)], input="md\n")
        assert result.exit_code == 0, result.exception
        assert json.loads(effect.read_text()) == "md"
        effect.unlink()
    result = CliRunner().invoke(native, [str(effect)], input="")
    assert result.exit_code != 0 and not effect.exists()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "prompt-consumer.py"
    with pytest.raises(TypeError, match="Prompt-backed enum parameters"):
        intpot.load(collection_source).write(
            destination, target, allow_scaffold=scaffold
        )
    assert not destination.exists() and not effect.exists()


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("prompt", [False, None])
def test_disabled_prompt_preserves_ordinary_collection(
    collection_source, tmp_path, monkeypatch, fallback, prompt
):
    collection_source.write_text(
        collection_source.read_text().replace(
            "typer.Option(None,'--to')", f"typer.Option(None,'--to',prompt={prompt!r})"
        )
    )
    test_collection_consumers_preserve_none_order_duplicates(
        collection_source, tmp_path, monkeypatch, fallback, False, "None"
    )


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("environment", [None, "md json", "invalid-choice"])
@pytest.mark.parametrize(
    "location",
    ["app", "command", "nested", "registration", "inherited", "empty", "callback"],
)
def test_automatic_environment_enum_options_refuse_before_writes(
    collection_source,
    tmp_path,
    monkeypatch,
    fallback,
    target,
    scaffold,
    environment,
    location,
):
    text = collection_source.read_text()
    args = []
    key = "ENUM_FIX_MODES"
    if location in ("app", "empty"):
        prefix = "" if location == "empty" else "ENUM_FIX"
        key = f"{prefix}_MODES"
        text = text.replace(
            "app=typer.Typer()",
            f"app=typer.Typer(context_settings={{'auto_envvar_prefix':{prefix!r}}})",
        )
    elif location == "callback":
        args = ["run"]
        key = "ENUM_FIX_RUN_MODES"
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'auto_envvar_prefix':'IGNORED'})",
        )
        text += "\n@app.callback(context_settings={'auto_envvar_prefix':'ENUM_FIX'})\ndef root_callback():\n pass\n"
    elif location == "command":
        text = text.replace(
            "@app.command()",
            "@app.command(context_settings={'auto_envvar_prefix':'ENUM_FIX'})",
        )
    else:
        args = ["group", "run"]
        key = "ENUM_FIX_RUN_MODES"
        if location == "nested":
            text = text.replace(
                "app=typer.Typer()",
                "app=typer.Typer(context_settings={'auto_envvar_prefix':'ENUM_FIX'})",
            )
        text += "\nchild=app\n"
        text += (
            "app=typer.Typer(context_settings={'auto_envvar_prefix':'ENUM_FIX'})\n"
            if location == "inherited"
            else "app=typer.Typer()\n"
        )
        text += (
            "app.add_typer(child,name='group',context_settings={'auto_envvar_prefix':'ENUM_FIX'})\n"
            if location == "registration"
            else "app.add_typer(child,name='group')\n"
        )
        if location == "inherited":
            key = "ENUM_FIX_GROUP_RUN_MODES"
    collection_source.write_text(text)
    if environment is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, environment)
    _, native = detect_source(collection_source)
    effect = tmp_path / "auto-env-effect.json"
    result = CliRunner().invoke(native, [*args, str(effect)])
    if environment == "invalid-choice":
        assert result.exit_code != 0 and not effect.exists()
    else:
        assert result.exit_code == 0, result.exception
        value = json.loads(effect.read_text())
        assert value == ["md", "json"] if environment else value in (None, [])
        effect.unlink()
    hits = []
    if fallback:

        def fail_tree():
            hits.append(True)
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "auto-env-consumer.py"
    with pytest.raises(TypeError, match="Environment-backed enum parameters"):
        intpot.load(collection_source).write(
            destination, target, allow_scaffold=scaffold
        )
    assert not destination.exists() and not effect.exists()
    if fallback:
        assert hits


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "location",
    [
        "sibling",
        "command_override",
        "flattened",
        "positional",
        "registration_override",
        "parent_resilient",
    ],
)
def test_automatic_environment_ignores_unaffected_enum_parameters(
    collection_source, tmp_path, monkeypatch, fallback, location
):
    text = collection_source.read_text()
    args = []
    scalar = location == "positional"
    if location in ("sibling", "flattened"):
        args = ["run"]
    if location == "sibling":
        text += "\nother=typer.Typer(context_settings={'auto_envvar_prefix':'OTHER'})\n@other.command()\ndef ping():\n typer.echo('pong')\napp.add_typer(other,name='other')\n"
    elif location == "command_override":
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'auto_envvar_prefix':'OTHER'})",
        )
        text = text.replace(
            "@app.command()",
            "@app.command(context_settings={'help_option_names':['--help']})",
        )
    elif location == "parent_resilient":
        args = ["child", "run"]
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'resilient_parsing':True})",
        )
        text += "\nchild=app\napp=typer.Typer()\napp.add_typer(child,name='child')\n"
    elif location == "registration_override":
        args = ["child", "run"]
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'auto_envvar_prefix':'OTHER'})",
        )
        text += "\nchild=app\napp=typer.Typer()\napp.add_typer(child,name='child',context_settings={})\n"
    elif location == "flattened":
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'auto_envvar_prefix':'OTHER'})",
        )
        text += "\nchild=app\napp=typer.Typer()\napp.add_typer(child)\n"
    else:
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'auto_envvar_prefix':'OTHER'})",
        )
        text = text.replace(
            "modes:list[Mode]=typer.Option(None,'--to')",
            "modes:Mode=typer.Argument(Mode.MD)",
        )
        text = text.replace("[m.value for m in modes]", "modes.value")
    collection_source.write_text(text)
    monkeypatch.setenv("OTHER_MODES", "invalid-choice")
    _, native = detect_source(collection_source)
    effect = tmp_path / "unaffected.json"
    result = CliRunner().invoke(native, [*args, str(effect)])
    if location == "flattened" and result.exit_code != 0:
        import typer.main

        # Older Typer omits unnamed subgroup commands altogether. This is a
        # source-only admission failure, not a generated-consumer failure.
        assert "run" not in typer.main.get_command(native).commands
        assert not effect.exists()
        pytest.skip("Source framework does not expose unnamed subgroup commands")
    assert result.exit_code == 0, result.exception
    omitted = json.loads(effect.read_text())
    assert omitted == "md" if scalar else omitted in (None, [])
    effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    loaded = intpot.load(collection_source)
    for target in ("api", "mcp"):
        namespace: dict[str, Any] = {"__name__": "unaffected_enum_consumer"}
        exec(getattr(loaded, "to_" + target)(), namespace)
        tool = (
            "child_run"
            if location in ("registration_override", "parent_resilient")
            else "run"
        )
        bodies = [
            ({"output": str(effect)}, omitted),
            (
                {
                    "output": str(effect),
                    "modes" if scalar else "to": "json" if scalar else ["json", "md"],
                },
                "json" if scalar else ["json", "md"],
            ),
        ]
        for body, expected in bodies:
            if target == "api":
                with TestClient(namespace["app"]) as client:
                    response = client.post("/" + tool, json=body)
                    assert response.status_code == 200, response.text
            else:

                async def invoke(server=namespace["mcp"], body=body, tool=tool):
                    async with Client(server) as client:
                        wire_body = dict(body)
                        if "to" in wire_body:
                            wire_body["modes"] = wire_body.pop("to")
                        response = await client.call_tool(tool, wire_body)
                        assert not getattr(
                            response, "is_error", getattr(response, "isError", False)
                        )

                asyncio.run(invoke())
            assert json.loads(effect.read_text()) == expected
            effect.unlink()


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("mapped", ["valid", "invalid", "callable"])
@pytest.mark.parametrize(
    "location",
    ["app", "command", "nested", "registration", "inherited", "callback", "reused"],
)
def test_context_default_map_enums_refuse_before_writes(
    collection_source,
    tmp_path,
    monkeypatch,
    fallback,
    target,
    scaffold,
    mapped,
    location,
):
    text = collection_source.read_text()
    value = "['md','json']" if mapped == "valid" else "['invalid-choice']"
    if mapped == "callable":
        text = text.replace(
            "app=typer.Typer()",
            "calls=[]\ndef mapped_default():\n calls.append('called')\n return ['md','json']\napp=typer.Typer()",
        )
        value = "mapped_default"
    mapping = "{'modes':" + value + "}"
    args = []
    if location == "app":
        text = text.replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'default_map':" + mapping + "})",
        )
    elif location == "command":
        text = text.replace(
            "@app.command()",
            "@app.command(context_settings={'default_map':" + mapping + "})",
        )
    elif location == "reused":
        args = ["mapped", "run"]
        text += (
            "\nchild=app\napp=typer.Typer()\napp.add_typer(child,name='plain')\napp.add_typer(child,name='mapped',context_settings={'default_map':{'run':"
            + mapping
            + "}})\n"
        )
    elif location == "callback":
        args = ["run"]
        text += (
            "\n@app.callback(context_settings={'default_map':{'run':"
            + mapping
            + "}})\ndef root_callback():\n pass\n"
        )
    else:
        args = ["group", "run"]
        if location == "nested":
            text = text.replace(
                "app=typer.Typer()",
                "app=typer.Typer(context_settings={'default_map':{'run':"
                + mapping
                + "}})",
            )
        text += "\nchild=app\n"
        text += (
            "app=typer.Typer(context_settings={'default_map':{'group':{'run':"
            + mapping
            + "}}})\n"
            if location == "inherited"
            else "app=typer.Typer()\n"
        )
        text += (
            "app.add_typer(child,name='group',context_settings={'default_map':{'run':"
            + mapping
            + "}})\n"
            if location == "registration"
            else "app.add_typer(child,name='group')\n"
        )
    collection_source.write_text(text)
    _, native = detect_source(collection_source)
    effect = tmp_path / "mapped-effect.json"
    result = CliRunner().invoke(native, [*args, str(effect), "--to", "json"])
    assert result.exit_code == 0 and json.loads(effect.read_text()) == ["json"]
    effect.unlink()
    result = CliRunner().invoke(native, [*args, str(effect)])
    if mapped == "invalid":
        assert result.exit_code != 0 and not effect.exists()
    else:
        assert result.exit_code == 0, result.exception
        assert json.loads(effect.read_text()) == ["md", "json"]
        effect.unlink()
    callback = sys.modules["enum_collection_app.main"].run
    calls = list(callback.__globals__.get("calls", []))
    hits = []
    if fallback:

        def fail_tree():
            hits.append(True)
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "mapped-consumer.py"
    with pytest.raises(TypeError, match="Context-backed enum defaults"):
        intpot.load(collection_source).write(
            destination, target, allow_scaffold=scaffold
        )
    assert not destination.exists() and not effect.exists()
    assert callback.__globals__.get("calls", []) == calls
    if fallback:
        assert hits


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "mapping",
    [
        "None",
        "{}",
        "{'modes':None}",
        "{'unrelated':lambda: (_ for _ in ()).throw(AssertionError('called'))}",
    ],
)
def test_unrelated_context_default_maps_preserve_collection(
    collection_source, tmp_path, monkeypatch, fallback, mapping
):
    collection_source.write_text(
        collection_source.read_text().replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'default_map':" + mapping + "})",
        )
    )
    test_collection_consumers_preserve_none_order_duplicates(
        collection_source, tmp_path, monkeypatch, fallback, False, "None"
    )


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "mapping", ["{}", "{'modes':None}", "{'unrelated':['invalid-choice']}"]
)
def test_context_default_map_overrides_do_not_reject_unaffected_collection(
    collection_source, tmp_path, monkeypatch, fallback, mapping
):
    text = collection_source.read_text().replace(
        "app=typer.Typer()",
        "app=typer.Typer(context_settings={'default_map':{'modes':['invalid-choice']}})",
    )
    text = text.replace(
        "@app.command()",
        "@app.command(context_settings={'default_map':" + mapping + "})",
    )
    collection_source.write_text(text)
    test_collection_consumers_preserve_none_order_duplicates(
        collection_source, tmp_path, monkeypatch, fallback, False, "None"
    )


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize("invalid", [False, True])
@pytest.mark.parametrize("boundary", ["parameter", "route", "settings"])
def test_custom_context_lookups_refuse_without_invoking_hooks(
    collection_source,
    tmp_path,
    monkeypatch,
    fallback,
    target,
    scaffold,
    invalid,
    boundary,
):
    text = collection_source.read_text()
    value = "['invalid-choice']" if invalid else "['md','json']"
    support = "calls=[]\nclass CustomMap(dict):\n def get(self,key,default=None):\n  calls.append(key)\n"
    args = []
    if boundary == "parameter":
        support += (
            "  if key=='modes':return "
            + value
            + "\n  return super().get(key,default)\n"
        )
        text = text.replace(
            "app=typer.Typer()",
            support + "app=typer.Typer(context_settings={'default_map':CustomMap()})",
        )
    elif boundary == "route":
        args = ["group", "run"]
        support += (
            "  if key=='group':return {'run':{'modes':"
            + value
            + "}}\n  return super().get(key,default)\n"
        )
        text = text.replace("app=typer.Typer()", support + "app=typer.Typer()")
        text += "\nchild=app\napp=typer.Typer(context_settings={'default_map':CustomMap()})\napp.add_typer(child,name='group')\n"
    else:
        support = (
            "calls=[]\nclass CustomSettings(dict):\n def __bool__(self):return True\n def items(self):\n  calls.append('items')\n  return {'default_map':{'modes':"
            + value
            + "}}.items()\n"
        )
        text = text.replace(
            "app=typer.Typer()",
            support + "app=typer.Typer(context_settings=CustomSettings())",
        )
    collection_source.write_text(text)
    _, native = detect_source(collection_source)
    effect = tmp_path / "custom-lookup.json"
    result = CliRunner().invoke(native, [*args, str(effect), "--to", "json"])
    assert result.exit_code == 0 and json.loads(effect.read_text()) == ["json"]
    effect.unlink()
    result = CliRunner().invoke(native, [*args, str(effect)])
    if invalid:
        assert result.exit_code != 0 and not effect.exists()
    else:
        assert result.exit_code == 0, result.exception
        assert json.loads(effect.read_text()) == ["md", "json"]
        effect.unlink()
    module = sys.modules["enum_collection_app.main"]
    before = list(module.calls)
    hits = []
    if fallback:

        def fail_tree():
            hits.append(True)
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "custom-consumer.py"
    with pytest.raises(
        TypeError,
        match=r"Context-backed enum defaults|Environment-backed enum parameters|Custom enum context settings",
    ):
        intpot.load(collection_source).write(
            destination, target, allow_scaffold=scaffold
        )
    assert not destination.exists() and not effect.exists()
    assert module.calls == before
    if fallback:
        assert hits


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("scaffold", [False, True])
@pytest.mark.parametrize(
    "behavior,location",
    [
        (behavior, location)
        for behavior in ("token_normalize_func", "resilient_parsing")
        for location in ("app", "command", "nested")
        if (behavior, location) != ("resilient_parsing", "nested")
    ],
)
def test_behavior_changing_enum_context_refuses_before_writes(
    collection_source,
    tmp_path,
    monkeypatch,
    fallback,
    target,
    scaffold,
    behavior,
    location,
):
    text = collection_source.read_text()
    settings = (
        "{'token_normalize_func':str.lower}"
        if behavior == "token_normalize_func"
        else "{'resilient_parsing':True}"
    )
    args = []
    if location == "command":
        text = text.replace(
            "@app.command()", "@app.command(context_settings=" + settings + ")"
        )
    else:
        text = text.replace(
            "app=typer.Typer()", "app=typer.Typer(context_settings=" + settings + ")"
        )
        if location == "nested":
            text += (
                "\nchild=app\napp=typer.Typer()\napp.add_typer(child,name='group')\n"
            )
            args = ["group", "run"]
    collection_source.write_text(text)
    _, native = detect_source(collection_source)
    effect = tmp_path / "context-behavior.json"
    result = CliRunner().invoke(native, [*args, str(effect), "--to", "json"])
    assert result.exit_code == 0 and json.loads(effect.read_text()) == ["json"]
    effect.unlink()
    value = "MD" if behavior == "token_normalize_func" else "invalid-choice"
    result = CliRunner().invoke(native, [*args, str(effect), "--to", value])
    if behavior == "resilient_parsing" and result.exit_code != 0:
        # Legacy Typer's builtin list converter raises before the body instead
        # of retaining None after Click suppresses the invalid-choice error.
        assert isinstance(result.exception, TypeError)
        assert str(result.exception) in (
            "'NoneType' object is not iterable",
            "object of type 'NoneType' has no len()",
        )
        assert not effect.exists()
    else:
        assert result.exit_code == 0, result.exception
        expected = ["md"] if behavior == "token_normalize_func" else None
        assert json.loads(effect.read_text()) == expected
        effect.unlink()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    destination = tmp_path / "behavior-consumer.py"
    with pytest.raises(TypeError, match="Custom enum context settings"):
        intpot.load(collection_source).write(
            destination, target, allow_scaffold=scaffold
        )
    assert not destination.exists() and not effect.exists()


@pytest.mark.parametrize("fallback", [False, True])
def test_disabled_enum_context_behavior_remains_convertible(
    collection_source, tmp_path, monkeypatch, fallback
):
    collection_source.write_text(
        collection_source.read_text().replace(
            "app=typer.Typer()",
            "app=typer.Typer(context_settings={'token_normalize_func':None,'resilient_parsing':False})",
        )
    )
    test_collection_consumers_preserve_none_order_duplicates(
        collection_source, tmp_path, monkeypatch, fallback, False, "None"
    )


@pytest.fixture
def collection_source(tmp_path, monkeypatch):
    package = tmp_path / "enum_collection_app"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "modes.py").write_text(
        "from enum import Enum\nclass Mode(str,Enum):\n MD='md'\n JSON='json'\n"
    )
    source = package / "main.py"
    source.write_text(
        "from pathlib import Path\nimport json\nimport typer\nfrom .modes import Mode\n"
        "app=typer.Typer()\n@app.command()\n"
        "def run(output:str,modes:list[Mode]=typer.Option(None,'--to')):\n"
        " value=None if modes is None else [m.value for m in modes]\n"
        " Path(output).write_text(json.dumps(value))\n typer.echo(json.dumps(value))\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield source
    for name in tuple(sys.modules):
        if name == package.name or name.startswith(package.name + "."):
            del sys.modules[name]


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("nullable", [False, True])
@pytest.mark.parametrize(
    "default", ["None", "[]", "[Mode.JSON,Mode.MD]", "(Mode.JSON,Mode.MD)"]
)
def test_collection_consumers_preserve_none_order_duplicates(
    collection_source, tmp_path, monkeypatch, fallback, nullable, default
):
    collection_source.write_text(
        collection_source.read_text().replace(
            "typer.Option(None,", f"typer.Option({default},"
        )
    )
    omitted = None if default == "None" else ([] if default == "[]" else ["json", "md"])
    if nullable:
        collection_source.write_text(
            collection_source.read_text()
            .replace("import typer\n", "import typer\nfrom typing import Optional\n")
            .replace("modes:list[Mode]", "modes:Optional[list[Mode]]")
            .replace("modes:Modes[Mode]", "modes:Optional[Modes[Mode]]")
        )
    _, native = detect_source(collection_source)
    effect = tmp_path / "effect.json"
    baseline = CliRunner().invoke(native, [str(effect)])
    assert baseline.exit_code == 0, baseline.exception
    native_omitted = json.loads(effect.read_text())
    if default == "None":
        # Typer 0.9 converts omission to []; modern Typer preserves None.
        assert native_omitted is None or native_omitted == []
        omitted = native_omitted
    else:
        assert native_omitted == omitted
    effect.unlink()
    cases = [
        ([], omitted),
        (["md"], ["md"]),
        (["md", "json"], ["md", "json"]),
        (["json", "md", "json"], ["json", "md", "json"]),
    ]
    for values, expected in cases:
        arguments = [str(effect)] + [
            part for value in values for part in ("--to", value)
        ]
        result = CliRunner().invoke(native, arguments)
        assert result.exit_code == 0, result.exception
        assert json.loads(effect.read_text()) == expected
        effect.unlink()
    result = CliRunner().invoke(native, [str(effect), "--to", "md", "--to", "invalid"])
    assert result.exit_code == 2 and not effect.exists()
    if fallback:

        def fail_tree():
            raise RuntimeError("force registered-command fallback")

        monkeypatch.setattr(native, "_get_command", fail_tree, raising=False)
    loaded = intpot.load(collection_source)
    namespace: dict[str, Any] = {"__name__": "collection_cli"}
    exec(CLIGenerator().generate(loaded.schema), namespace)
    for values, expected in cases:
        result = CliRunner().invoke(
            namespace["app"],
            [str(effect)] + [part for value in values for part in ("--to", value)],
        )
        assert result.exit_code == 0, result.exception
        assert json.loads(effect.read_text()) == expected
        effect.unlink()
    namespace = {"__name__": "collection_api"}
    exec(loaded.to_api(), namespace)
    with TestClient(namespace["app"]) as client:
        for values, expected in cases:
            body = {"output": str(effect)}
            if values:
                body["to"] = values
            response = client.post("/run", json=body)
            assert response.status_code == 200, response.text
            assert json.loads(effect.read_text()) == expected
            effect.unlink()
        response = client.post("/run", json={"output": str(effect), "to": []})
        assert response.status_code == 200 and json.loads(effect.read_text()) == []
        effect.unlink()
        # Null is outside the CLI wire domain. Compare the installed FastAPI's
        # own type/default semantics rather than imposing one version's behavior.
        mode_class = sys.modules["enum_collection_app.modes"].Mode
        native_default = (
            None if omitted is None else [mode_class(value) for value in omitted]
        )

        def null_control(output=Body(...), modes=Body(native_default, alias="to")):
            return None if modes is None else [mode.value for mode in modes]

        native_annotation: Any = list.__class_getitem__(mode_class)
        if nullable:
            native_annotation = native_annotation | type(None)
        null_control.__annotations__ = {"output": str, "modes": native_annotation}
        control_app = FastAPI()
        control_app.post("/control")(null_control)
        with TestClient(control_app) as native_client:
            control = native_client.post(
                "/control", json={"output": str(effect), "to": None}
            )
        response = client.post("/run", json={"output": str(effect), "to": None})
        assert response.status_code == control.status_code
        if response.status_code == 200:
            assert json.loads(effect.read_text()) == control.json()
            effect.unlink()
        else:
            assert response.status_code == 422 and not effect.exists()
        for invalid in ("md", ["md", "invalid"], [None], [0]):
            response = client.post("/run", json={"output": str(effect), "to": invalid})
            assert response.status_code == 422, response.text
            assert not effect.exists()
    namespace = {"__name__": "collection_mcp"}
    exec(loaded.to_mcp(), namespace)

    async def check():
        async with Client(namespace["mcp"]) as client:
            for values, expected in cases:
                body = {"output": str(effect)}
                if values:
                    body["modes"] = values
                result = await client.call_tool("run", body)
                assert json.loads(result.content[0].text) == expected
                assert json.loads(effect.read_text()) == expected
                effect.unlink()
            if nullable:
                result = await client.call_tool(
                    "run", {"output": str(effect), "modes": None}
                )
                assert json.loads(result.content[0].text) is None
                assert json.loads(effect.read_text()) is None
                effect.unlink()
            for invalid in (
                "md",
                ["md", "invalid"],
                [None],
                [0],
                *([] if nullable else [None]),
            ):
                try:
                    result = await client.call_tool(
                        "run", {"output": str(effect), "modes": invalid}
                    )
                except ToolError:
                    pass
                else:
                    assert getattr(
                        result, "is_error", getattr(result, "isError", False)
                    )
                assert not effect.exists()

    asyncio.run(check())
