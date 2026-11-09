from __future__ import annotations

import pytest
from typer.testing import CliRunner

import intpot
from intpot.cli import app
from intpot.core.callbacks import UnsupportedCLIParameterCallbackError
from intpot.core.informational_callbacks import capture_informational_callback


def test_native_annotation_provider_keeps_refusal_before_writes(tmp_source):
    path = tmp_source("""import typer
calls=[]
def info(value: bool):
    calls.append(value)
    if value:
        print("INFO")
        raise typer.Exit()
app=typer.Typer()
@app.command()
def convert(version: bool=typer.Option(False,callback=info,is_eager=True)):
    typer.echo("business")
""")
    (path.parent / "__init__.py").write_text("")
    loaded = intpot.load(path)
    callback = loaded.app.registered_commands[0].callback.__globals__["info"]
    if getattr(callback, "__annotate__", None) is None:
        pytest.skip(
            "native provider refusal control requires an actual annotation provider"
        )
    assert capture_informational_callback(callback) is None
    parameter = loaded.schema.tools[0].parameters[0]
    assert parameter.informational_callback is None and parameter.unsupported_callback
    for target in ("api", "mcp"):
        destination = path.parent / ("not-created-" + target) / "generated.py"
        with pytest.raises(UnsupportedCLIParameterCallbackError):
            loaded.project(
                target, callback_policy="exclusive-informational", allow_scaffold=True
            )
        with pytest.raises(UnsupportedCLIParameterCallbackError):
            loaded.write(
                destination,
                target,
                callback_policy="exclusive-informational",
                allow_scaffold=True,
            )
        result = CliRunner().invoke(
            app,
            [
                "to",
                target,
                str(path),
                "--callback-policy",
                "exclusive-informational",
                "--allow-scaffold",
                "-o",
                str(destination),
            ],
        )
        assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
        assert not destination.parent.exists()
    assert callback.__globals__["calls"] == []
