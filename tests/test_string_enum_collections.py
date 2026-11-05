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
