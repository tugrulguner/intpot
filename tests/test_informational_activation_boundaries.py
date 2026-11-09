from __future__ import annotations

import pytest
from typer.testing import CliRunner

import intpot
from intpot.core.callbacks import UnsupportedCLIParameterCallbackError


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_shadowed_boolean_callback_annotation_refuses(tmp_source, target):
    path = tmp_source("""from pathlib import Path
import typer
from .callbacks import info_callback
app=typer.Typer()
@app.command()
def convert(output: str, info: bool=typer.Option(False, callback=info_callback, is_eager=True)):
    Path(output).write_text("body")
    typer.echo("body")
""")
    (path.parent / "__init__.py").write_text("")
    (path.parent / "callbacks.py").write_text("""from __future__ import annotations
import typer
from typer import Context as bool

def info_callback(value: bool):
    if value:
        print("CONTEXT INFORMATION")
        raise typer.Exit()
""")
    loaded = intpot.load(path)
    native = CliRunner().invoke(loaded.app, [])
    assert native.exit_code == 0 and "CONTEXT INFORMATION" in native.output
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        getattr(loaded, "to_" + target)(callback_policy="exclusive-informational")


@pytest.mark.parametrize(
    "configuration,extra,environment",
    [
        ("None", ', envvar="INFO_FLAG"', {"INFO_FLAG": "1"}),
        ('{"auto_envvar_prefix":"INFO"}', "", {"INFO_INFO": "1"}),
        ('{"default_map":{"info":True}}', "", {}),
    ],
)
@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize("fallback", [False, True])
def test_dynamic_informational_activation_refuses(
    tmp_source, configuration, extra, environment, fallback, target, monkeypatch
):
    path = tmp_source(
        """from __future__ import annotations
from pathlib import Path
import typer

def info_callback(value: bool):
    if value:
        print("INFORMATION")
        raise typer.Exit()

app=typer.Typer(context_settings="""
        + configuration
        + """)
@app.command()
def convert(output: str, info: bool=typer.Option(False, callback=info_callback, is_eager=True"""
        + extra
        + """)):
    Path(output).write_text("body")
    typer.echo("body")
"""
    )
    (path.parent / "__init__.py").write_text("")
    loaded = intpot.load(path)
    native = CliRunner().invoke(loaded.app, [], env=environment)
    assert native.exit_code == 0 and "INFORMATION" in native.output, (
        native.output,
        native.exception,
    )
    from intpot.core.inspectors.cli import CLIInspector

    registered_hits = []
    original_registered = CLIInspector._extract_registered_app

    def registered(self, *args, **kwargs):
        registered_hits.append(True)
        return original_registered(self, *args, **kwargs)

    monkeypatch.setattr(CLIInspector, "_extract_registered_app", registered)
    callback = loaded.app.registered_commands[0].callback.__globals__["info_callback"]
    provider = getattr(callback, "__annotate__", None) is not None
    hits = []
    if fallback:

        def fail():
            hits.append(True)
            raise RuntimeError("force fallback")

        loaded.app._get_command = fail
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        getattr(loaded, "to_" + target)(callback_policy="exclusive-informational")
    if provider:
        # Preflight must choose registered inspection before even the forced
        # native-constructor hook can inspect a parameter callback's provider.
        assert not hits and registered_hits
    else:
        assert bool(hits) == fallback
        assert bool(registered_hits) == fallback
