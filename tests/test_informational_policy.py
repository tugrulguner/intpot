from __future__ import annotations

import hashlib
import importlib
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from intpot.core.informational_callbacks import capture_informational_callback
from intpot.core.informational_policy import qualify_informational_callback


def _candidate(tmp_path: Path, body: str, extra: str = ""):
    name = "policy_fixture_" + uuid.uuid4().hex
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("")
    source = (
        "from __future__ import annotations\nimport typer\nfrom typer import Exit\ncalls=[]\n"
        + extra
        + "\ndef callback(value: bool):\n"
        + textwrap.indent(textwrap.dedent(body).strip(), "    ")
        + "\n"
    )
    path = package / "mod.py"
    path.write_text(source)
    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module(name + ".mod")
    finally:
        sys.path.remove(str(tmp_path))
    spec = capture_informational_callback(module.callback)
    assert spec is not None
    return module, spec, path


@pytest.mark.parametrize(
    "exit_expression", ["Exit()", "Exit(0)", "Exit(code=0)", "typer.Exit()", "Exit"]
)
def test_qualifies_exit_without_calling(
    tmp_path, exit_expression, eager_callback_annotations
):
    module, spec, path = _candidate(
        tmp_path, "if value:\n    calls.append(value)\n    raise " + exit_expression
    )
    assert (
        qualify_informational_callback(spec)
        == hashlib.sha256(path.read_text().encode()).hexdigest()
    )
    assert module.calls == []
    # This invocation is a native control, never performed by the qualifier.
    assert module.callback(False) is None and module.callback(None) is None
    assert module.calls == []


@pytest.mark.parametrize(
    "body",
    [
        "if value:\n    pass",
        "if value:\n    raise Exit(1)",
        "if value:\n    return None\n    raise Exit()",
        "if value:\n    raise custom_exit()",
        "if value:\n    raise Exit()\nelse:\n    pass",
        "return None",
        "if value:\n    raise Exit(code=1)",
        "if value:\n    Exit = ValueError\n    raise Exit()",
        "if value:\n    typer = object()\n    raise typer.Exit()",
        "if value:\n    typer.Exit = ValueError\n    raise typer.Exit()",
        "if value:\n    global calls\n    raise Exit()",
    ],
)
def test_rejects_nonconforming_body(tmp_path, body, eager_callback_annotations):
    module, spec, _ = _candidate(tmp_path, body)
    with pytest.raises(TypeError):
        qualify_informational_callback(spec)
    assert module.calls == []


def test_stale_source_rejected(tmp_path, eager_callback_annotations):
    _, spec, path = _candidate(tmp_path, "if value:\n    raise Exit()")
    path.write_text(path.read_text().replace("raise Exit()", "pass"))
    with pytest.raises(TypeError):
        qualify_informational_callback(spec)


def test_subclass_cannot_execute_resolution_hook():
    from intpot.core.informational_callbacks import InformationalCallbackSpec

    calls = []

    class HookedSpec(InformationalCallbackSpec):
        def resolve(self):
            calls.append(True)
            raise RuntimeError("untrusted resolution hook")

    spec = HookedSpec("some.package", "callback", "0" * 64)
    with pytest.raises(TypeError):
        qualify_informational_callback(spec)
    assert calls == []


@pytest.mark.parametrize("replacement", [None, ValueError])
def test_mutated_framework_exit_is_not_certified(
    tmp_path, monkeypatch, replacement, eager_callback_annotations
):
    import typer

    module, spec, _ = _candidate(tmp_path, "if value:\n    raise Exit()")
    monkeypatch.setattr(typer, "Exit", replacement)
    module.Exit = replacement
    with pytest.raises(TypeError):
        qualify_informational_callback(spec)
    assert module.calls == []


def test_rebound_exit_refused_without_calling(tmp_path, eager_callback_annotations):
    module, spec, _ = _candidate(tmp_path, "if value:\n    raise Exit()")
    module.Exit = ValueError
    with pytest.raises(TypeError):
        qualify_informational_callback(spec)
    assert module.calls == []
