from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

import intpot
from intpot.core.inspectors._utils import extract_source_imports


@pytest.fixture
def packaged_app(tmp_path, monkeypatch):
    name = "relative_case_" + uuid.uuid4().hex
    root = tmp_path / name
    nested = root / "nested"
    nested.mkdir(parents=True)
    helper = "def format_text(value: str, separator: str) -> str:\n    return value.replace(' ', separator)\n"
    for folder in (root, nested):
        (folder / "__init__.py").write_text("")
        (folder / "helper.py").write_text(helper)
    monkeypatch.syspath_prepend(str(tmp_path))

    def load(
        statement="from . import helper as helper_module",
        expression="helper_module.format_text(text_, separator)",
    ):
        (nested / "cli.py").write_text(
            "import typer\n" + statement + "\napp = typer.Typer()\n"
            "@app.command()\n"
            "def slug(text_: str, separator: str = '-') -> None:\n"
            f"    typer.echo({expression})\n"
        )
        module = importlib.import_module(name + ".nested.cli")
        return module, module.app.registered_commands[0].callback

    yield load
    for key in list(sys.modules):
        if key == name or key.startswith(name + "."):
            sys.modules.pop(key, None)


@pytest.mark.parametrize(
    ("statement", "expression"),
    [
        (
            "from . import helper as helper_module",
            "helper_module.format_text(text_, separator)",
        ),
        ("from .helper import format_text as render", "render(text_, separator)"),
        ("from ..helper import format_text as render", "render(text_, separator)"),
        (
            "if True:\n    from .helper import format_text as render",
            "render(text_, separator)",
        ),
    ],
)
def test_imported_packaged_app_relative_imports_work_in_generated_consumers(
    packaged_app, statement, expression
):
    module, _ = packaged_app(statement, expression)
    selected = intpot.load(module.app)
    api: dict[str, Any] = {"__name__": "generated_api"}
    exec(selected.to_api(), api)
    with TestClient(api["app"]) as client:
        response = client.post("/slug", json={"text_": "a b"})
        assert response.status_code == 200
        assert response.json() == {"result": "a-b"}
        assert client.post("/slug", json={"text_": "a b", "separator": "_"}).json() == {
            "result": "a_b"
        }
    mcp = {"__name__": "generated_mcp"}
    exec(selected.to_mcp(), mcp)

    async def call():
        async with Client(mcp["mcp"]) as client:
            result = await client.call_tool("slug", {"text_": "a b"})
            assert result.content[0].text == "a-b"

    asyncio.run(call())


@pytest.mark.parametrize("package_value", [None, "", "missing_package", 123])
def test_missing_or_wrong_package_does_not_certify_import(
    packaged_app, monkeypatch, package_value
):
    _, fn = packaged_app()
    monkeypatch.setitem(fn.__globals__, "__package__", package_value)
    assert not any("helper" in line for line in extract_source_imports(fn))


def test_overdeep_package_context_does_not_certify_import(packaged_app, monkeypatch):
    _, fn = packaged_app(
        "from ..helper import format_text as render", "render(text_, separator)"
    )
    monkeypatch.setitem(fn.__globals__, "__package__", "single_level")
    assert not any("helper" in line for line in extract_source_imports(fn))


def test_unloaded_module_is_not_imported_to_probe_binding(packaged_app, monkeypatch):
    _, fn = packaged_app(
        "from .helper import format_text as render", "render(text_, separator)"
    )
    module_name = fn.__globals__["__package__"] + ".helper"
    monkeypatch.delitem(sys.modules, module_name)
    assert not any("helper" in line for line in extract_source_imports(fn))
    assert module_name not in sys.modules


def test_inactive_relative_import_is_not_probed(packaged_app):
    module, fn = packaged_app("if False:\n    from . import helper as helper_module")
    child = fn.__globals__["__package__"] + ".helper"
    assert not any("helper" in line for line in extract_source_imports(fn))
    assert child not in sys.modules
    with pytest.raises(intpot.MissingBindingError, match="helper_module"):
        intpot.load(module.app).to_api()
    assert child not in sys.modules


def test_missing_export_does_not_invoke_dynamic_getattr(packaged_app, monkeypatch):
    _, fn = packaged_app()
    parent = sys.modules[fn.__globals__["__package__"]]
    monkeypatch.delattr(parent, "helper")
    calls = []

    def dynamic(name):
        calls.append(name)
        raise AttributeError(name)

    monkeypatch.setattr(parent, "__getattr__", dynamic, raising=False)
    assert not any("helper" in line for line in extract_source_imports(fn))
    assert calls == []


@pytest.mark.parametrize("scaffold", [False, True])
def test_unverified_relative_binding_refuses_before_write(
    packaged_app, monkeypatch, tmp_path, scaffold
):
    module, fn = packaged_app()
    monkeypatch.setitem(fn.__globals__, "__package__", None)
    selected = intpot.load(module.app)
    for target in ("api", "mcp"):
        output = tmp_path / (target + ".py")
        with pytest.raises(intpot.MissingBindingError, match="helper_module"):
            selected.write(str(output), target, allow_scaffold=scaffold)
        assert not output.exists()


def test_rebound_relative_import_is_not_certified(packaged_app, monkeypatch):
    _, fn = packaged_app()
    monkeypatch.setitem(fn.__globals__, "helper_module", object())
    assert not any("helper" in line for line in extract_source_imports(fn))


def test_rebound_parent_export_is_not_replaced_by_cached_child(
    packaged_app, monkeypatch
):
    _, fn = packaged_app()
    parent = sys.modules[fn.__globals__["__package__"]]
    monkeypatch.setattr(parent, "helper", object())
    assert not any("helper" in line for line in extract_source_imports(fn))
