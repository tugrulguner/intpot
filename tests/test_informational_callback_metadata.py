from __future__ import annotations

import dataclasses
import json

import pytest

import intpot


def _loaded(tmp_source, declaration=None):
    declaration = (
        declaration or "value: bool = typer.Option(False, callback=info, is_eager=True)"
    )
    path = tmp_source(
        "import typer\nfrom typing import Annotated, Optional\nfrom .callbacks import info\napp=typer.Typer()\n@app.command()\ndef run("
        + declaration
        + "):\n    return str(value)\n"
    )
    (path.parent / "__init__.py").write_text("")
    (path.parent / "callbacks.py").write_text(
        'from __future__ import annotations\ncalls=[]\ndef info(value: bool):\n    calls.append(value)\n    if value:\n        print("INFO")\n'
    )
    return intpot.load(path)


def test_custom_annotation_provider_is_not_executed(tmp_source):
    import sys

    from intpot.core.informational_callbacks import capture_informational_callback

    loaded = _loaded(tmp_source)
    spec = loaded.schema.tools[0].parameters[0].informational_callback
    assert spec is not None
    callback = sys.modules[spec.module].info
    calls = []

    def annotate(format):
        calls.append(format)
        return {"value": bool}

    callback.__annotate__ = annotate
    assert capture_informational_callback(callback) is None
    assert calls == []


def test_runtime_copy_preserves_callback_evidence(tmp_source):
    from intpot.runtime import _copy_tool_info

    loaded = _loaded(tmp_source)
    original = loaded.tools[0]
    copied = _copy_tool_info(original)
    assert (
        copied.parameters[0].informational_callback
        is original.parameters[0].informational_callback
    )
    assert copied.parameters[0].informational_callback is not None


def test_canonical_callback_metadata_rejects_mutable_payload():
    from intpot.core.models import ParameterSchema

    with pytest.raises(TypeError, match="immutable"):
        ParameterSchema("x", "bool", default=False, informational_callback={})  # type: ignore[arg-type]


def test_supported_eager_bool_callback_is_pure_candidate_metadata(tmp_source):
    package = tmp_source("""\
import typer
from .callbacks import verbose
app = typer.Typer()
@app.command()
def run(verbose: bool = typer.Option(False, "--verbose", is_eager=True, callback=verbose)):
    return str(verbose)
""")
    callbacks = package.parent / "callbacks.py"
    callbacks.write_text(
        "from __future__ import annotations\ndef verbose(value: bool) -> bool:\n    return value\n"
    )
    (package.parent / "__init__.py").write_text("")
    loaded = intpot.load(package)
    parameter = loaded.schema.tools[0].parameters[0]
    assert parameter.informational_callback is not None
    assert parameter.informational_callback.module == f"{package.parent.name}.callbacks"
    assert parameter.unsupported_callback is True
    assert "informational_callback" in parameter.to_dict()
    assert (
        json.loads(json.dumps(parameter.to_dict()))["informational_callback"]
        == parameter.informational_callback.to_dict()
    )
    assert dataclasses.is_dataclass(parameter.informational_callback)


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize(
    "declaration",
    [
        "value: bool = typer.Option(False, callback=info, is_eager=True)",
        "value: bool | None = typer.Option(None, callback=info, is_eager=True)",
        "value: Annotated[bool, typer.Option(callback=info, is_eager=True)] = False",
        "value: Annotated[Optional[bool], typer.Option(callback=info, is_eager=True)] = None",
    ],
)
def test_capture_is_detached_and_never_calls_callback(
    tmp_source, fallback, declaration
):
    import sys

    from intpot.core.callbacks import UnsupportedCLIParameterCallbackError
    from intpot.core.informational_callbacks import InformationalCallbackSpec

    loaded = _loaded(tmp_source, declaration)
    hits = []
    if fallback:

        def fail():
            hits.append(True)
            raise RuntimeError("forced registered fallback")

        loaded.app._get_command = fail
    else:
        import typer.main

        def constructed():
            command = typer.main.get_command(loaded.app)
            hits.append(True)
            return command

        loaded.app._get_command = constructed
    parameter = loaded.schema.tools[0].parameters[0]
    spec = parameter.informational_callback
    assert spec is not None
    owner = sys.modules[spec.module]
    assert owner.calls == []
    assert spec.resolve() is owner.info
    assert (
        InformationalCallbackSpec.from_dict(json.loads(json.dumps(spec.to_dict())))
        == spec
    )
    assert hash(parameter) == hash(type(parameter).from_info(parameter.to_info()))
    detached = loaded.tools
    assert detached[0].parameters[0].informational_callback is spec
    detached[0].parameters[0].informational_callback = None
    assert loaded.schema.tools[0].parameters[0].informational_callback is spec
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.module = "other.module"  # type: ignore[misc]
    for scaffold in (False, True):
        with pytest.raises(UnsupportedCLIParameterCallbackError):
            loaded.to_api(allow_scaffold=scaffold)
        with pytest.raises(UnsupportedCLIParameterCallbackError):
            loaded.to_mcp(allow_scaffold=scaffold)
    assert owner.calls == []
    assert hits == [True]


@pytest.mark.parametrize("change", ["rebind", "code"])
def test_captured_identity_detects_callback_change(tmp_source, change):
    import sys
    import types

    loaded = _loaded(tmp_source)
    spec = loaded.schema.tools[0].parameters[0].informational_callback
    assert spec is not None
    owner = sys.modules[spec.module]
    original = owner.info
    if change == "rebind":
        replacement = types.FunctionType(
            original.__code__, original.__globals__, original.__name__
        )
        replacement.__annotations__ = dict(original.__annotations__)
        owner.info = replacement
    else:
        original.__code__ = (lambda value: None).__code__
    with pytest.raises(TypeError, match="changed"):
        spec.resolve()
    assert owner.calls == []


@pytest.mark.parametrize(
    "declaration",
    [
        "value: bool = typer.Option(False, callback=info, is_eager=False)",
        "value: bool = typer.Option(True, callback=info, is_eager=True)",
        "value: str = typer.Option(None, callback=info, is_eager=True)",
    ],
)
@pytest.mark.parametrize("fallback", [False, True])
def test_unqualified_parameter_keeps_only_refusal(tmp_source, declaration, fallback):
    loaded = _loaded(tmp_source, declaration)
    if fallback:
        loaded.app._get_command = lambda: (_ for _ in ()).throw(
            RuntimeError("fallback")
        )
    parameter = loaded.schema.tools[0].parameters[0]
    assert parameter.informational_callback is None
    assert parameter.unsupported_callback
    assert "informational_callback" not in parameter.to_dict()


def test_decoding_does_not_import_or_coerce_data():
    import sys

    from intpot.core.informational_callbacks import InformationalCallbackSpec

    module = "unloaded_callback_package.callbacks"
    assert module not in sys.modules
    spec = InformationalCallbackSpec.from_dict(
        {"module": module, "export": "info", "code_digest": "0" * 64}
    )
    assert module not in sys.modules
    with pytest.raises(TypeError):
        spec.resolve()
    assert module not in sys.modules
    with pytest.raises(ValueError):
        InformationalCallbackSpec.from_dict(
            {"module": 42, "export": "info", "code_digest": "0" * 64}
        )


@pytest.mark.parametrize(
    "source",
    [
        "def info(value): pass",
        "async def info(value: bool): pass",
        "def info(value: bool, ctx=None): pass",
        "def info(*value: bool): pass",
        "def outer():\n    captured=False\n    def info(value: bool): return captured\n    return info\ninfo=outer()",
    ],
)
def test_unqualified_callable_capture_is_conservative(tmp_source, source):
    import sys

    from intpot.core.informational_callbacks import capture_informational_callback

    loaded = _loaded(tmp_source)
    spec = loaded.schema.tools[0].parameters[0].informational_callback
    assert spec is not None
    owner = sys.modules[spec.module]
    exec(source, vars(owner))
    assert capture_informational_callback(owner.info) is None
