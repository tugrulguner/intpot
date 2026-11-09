from __future__ import annotations

import pytest
from typer.testing import CliRunner

import intpot
from intpot.cli import app
from intpot.core.callbacks import UnsupportedCLIParameterCallbackError


@pytest.mark.parametrize(
    "declaration",
    [
        "version: bool=typer.Option(False,callback=info,is_eager=True)",
        "version: Annotated[bool, typer.Option(callback=info,is_eager=True)] = False",
        "version: bool=ExtendedOption(default=False,callback=info,is_eager=True)",
        "version: Annotated[bool, INFO_OPTION] = False",
    ],
)
@pytest.mark.parametrize("callback_reference", ["info", "wrapped"])
def test_public_inspection_does_not_evaluate_parameter_callback_provider(
    tmp_source, declaration, callback_reference
):
    path = tmp_source(
        """import typer
from typing import Annotated
class ExtendedOption(typer.models.OptionInfo):
    pass
provider_calls=[]
callback_calls=[]
def info(value: bool):
    callback_calls.append(value)
    if value:
        print('INFO')
        raise typer.Exit()
def annotations(format):
    provider_calls.append(format)
    return {'value': bool}
info.__annotate__=annotations
def wrapped(*args, **kwargs):
    return info(*args, **kwargs)
wrapped.__wrapped__=info
INFO_OPTION=typer.Option(callback=info,is_eager=True)
WRAPPED_OPTION=typer.Option(callback=wrapped,is_eager=True)
app=typer.Typer()
@app.command()
def convert(version: bool=typer.Option(False,callback=info,is_eager=True)):
    typer.echo('business')
""".replace(
            "version: bool=typer.Option(False,callback=info,is_eager=True)",
            declaration.replace(
                "callback=info", "callback=" + callback_reference
            ).replace("INFO_OPTION", callback_reference.upper() + "_OPTION"),
        )
    )
    (path.parent / "__init__.py").write_text("")
    loaded = intpot.load(path)
    namespace = loaded.app.registered_commands[0].callback.__globals__
    assert namespace["provider_calls"] == []
    parameter = loaded.schema.tools[0].parameters[0]
    assert namespace["provider_calls"] == []
    assert parameter.unsupported_callback and parameter.informational_callback is None
    assert {
        item["code"]
        for item in loaded.assess(callback_policy="exclusive-informational")[
            "diagnostics"
        ]
    } == {"unsupported_cli_parameter_callback"}
    for target in ("api", "mcp"):
        destination = path.parent / ("not-created-" + target) / "generated.py"
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
        assert result.exit_code == 1, (result.output, result.exception)
        assert not destination.parent.exists()
    inspected = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert inspected.exit_code == 0, (inspected.output, inspected.exception)
    assert namespace["provider_calls"] == namespace["callback_calls"] == []


def test_group_callback_provider_is_checked_before_native_tree(tmp_source):
    path = tmp_source("""import typer
provider_calls=[]
def info(value: bool):
    if value:
        raise typer.Exit()
def annotations(format):
    provider_calls.append(format)
    return {'value': bool}
info.__annotate__=annotations
app=typer.Typer()
@app.callback()
def group(version: bool=typer.Option(False,callback=info,is_eager=True)):
    pass
@app.command()
def run():
    typer.echo('business')
""")
    (path.parent / "__init__.py").write_text("")
    loaded = intpot.load(path)
    namespace = loaded.app.registered_commands[0].callback.__globals__
    assert len(loaded.schema.tools) == 1
    assert namespace["provider_calls"] == []
