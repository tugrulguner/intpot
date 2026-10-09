"""Source CLI parameter callbacks must not disappear during conversion."""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

import intpot
import intpot.converter as converter

SOURCE = """\
import typer
app = typer.Typer()
def validate(value: str) -> str:
    if value != "Camila":
        raise typer.BadParameter("Only Camila is allowed")
    return value.upper()
@app.command()
def greet(name: str = typer.Option(..., callback=validate)) -> str:
    typer.echo(name)
    return name
"""


def test_callback_inspection_remains_available_but_conversion_refuses(tmp_source):
    path = tmp_source(SOURCE)
    loaded = intpot.load(path)
    rejected = CliRunner().invoke(loaded.app, ["--name", "Rick"])
    assert rejected.exit_code == 2
    assert "Only Camila is allowed" in rejected.output
    accepted = CliRunner().invoke(loaded.app, ["--name", "Camila"])
    assert accepted.exit_code == 0
    assert accepted.stdout == "CAMILA\n"
    parameter = loaded.tools[0].parameters[0]
    assert parameter.unsupported_callback is True
    assert (
        json.loads(json.dumps(loaded.schema.to_dict()))["tools"][0]["parameters"][0][
            "unsupported_callback"
        ]
        is True
    )
    with pytest.raises(
        converter.UnsupportedCLIParameterCallbackError, match=r"greet\.name.*api"
    ):
        loaded.to_api()


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("kind", ["Option", "Argument"])
def test_callback_metadata_covers_typer_declarations(
    tmp_source, monkeypatch, annotated, fallback, kind
):
    declaration = (
        f"name: Annotated[str, typer.{kind}(callback=validate)]"
        if annotated
        else f"name: str = typer.{kind}(..., callback=validate)"
    )
    path = tmp_source(
        SOURCE.replace(
            "import typer", "import typer\nfrom typing import Annotated"
        ).replace("name: str = typer.Option(..., callback=validate)", declaration)
    )
    loaded = intpot.load(path)
    if fallback:
        import typer.main

        def cannot_build(*args, **kwargs):
            raise RuntimeError("exercise registered-command fallback")

        monkeypatch.setattr(typer.main, "get_group", cannot_build)
    assert loaded.tools[0].parameters[0].unsupported_callback is True
    with pytest.raises(
        intpot.UnsupportedCLIParameterCallbackError, match=r"greet\.name.*mcp"
    ):
        loaded.to_mcp()


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_all_conversion_paths_refuse_callback(tmp_source, tmp_path, target):
    from intpot.core.generators.api import APIGenerator
    from intpot.core.generators.mcp import MCPGenerator
    from intpot.core.models import SourceType

    loaded = intpot.load(tmp_source(SOURCE))
    output = tmp_path / "output" / "generated.py"
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError, match=target):
        loaded.project(target)
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError, match=target):
        loaded.write(output, target)
    assert not output.parent.exists()
    generator = APIGenerator() if target == "api" else MCPGenerator()
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError, match=target):
        generator.generate(loaded.schema)
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError, match=target):
        generator.generate(loaded.tools)
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError, match=target):
        converter._prepare_tools_for_target(
            SourceType.CLI, loaded.tools, SourceType(target)
        )


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_cli_refuses_before_any_directory_output(tmp_source, tmp_path, target):
    import inspect

    from intpot.cli import app

    runner_options: dict[str, Any] = (
        {"mix_stderr": False}
        if "mix_stderr" in inspect.signature(CliRunner).parameters
        else {}
    )
    runner = CliRunner(**runner_options)
    source = tmp_path / "inputs"
    source.mkdir()
    (source / "a_plain.py").write_text(
        SOURCE.replace("typer.Option(..., callback=validate)", '"world"')
    )
    (source / "z_callback.py").write_text(SOURCE)
    output = tmp_path / "outputs"
    result = runner.invoke(app, ["to", target, str(source), "--output", str(output)])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "greet.name" in result.stderr
    assert "callback validation or transformation" in result.stderr
    assert not output.exists()
    assert "Traceback" not in result.output
    dry = runner.invoke(
        app, ["to", target, str(source), "--output", str(output), "--dry-run"]
    )
    assert dry.exit_code == 1
    assert dry.stdout == ""
    assert "greet.name" in dry.stderr
    assert not output.exists()
    inspected = runner.invoke(app, ["inspect", str(source / "z_callback.py"), "--json"])
    assert inspected.exit_code == 0
    assert '"unsupported_callback": true' in inspected.stdout


def test_callback_marker_round_trips_without_changing_legacy_positions():
    from intpot import ParameterSchema
    from intpot.core.models import ParameterInfo

    plain = ParameterSchema("name")
    marked = ParameterSchema("name", unsupported_callback=True)
    assert plain != marked
    assert len({plain, marked}) == 2
    assert marked.to_info().unsupported_callback is True
    assert ParameterSchema.from_info(marked.to_info()) == marked
    assert json.loads(json.dumps(marked.to_dict()))["unsupported_callback"] is True
    assert "unsupported_callback" not in plain.to_dict()
    legacy = ParameterInfo(
        "name", "str", "value", "help", None, None, None, "alias", ["--alias"]
    )
    assert legacy.aliases == ["--alias"]
    assert legacy.unsupported_callback is False


@pytest.mark.parametrize("target", ["api", "mcp"])
def test_plain_parameter_still_generates_an_executable_target(tmp_source, target):
    import asyncio

    from fastapi.testclient import TestClient

    path = tmp_source("""\
import typer
app = typer.Typer()
@app.command()
def greet(name: str = "world"):
    typer.echo(f"Hello {name}")
""")
    loaded = intpot.load(path)
    assert loaded.tools[0].parameters[0].unsupported_callback is False
    code = getattr(loaded, f"to_{target}")()
    namespace: dict[str, Any] = {"__name__": "generated_control"}
    exec(compile(code, "generated_control.py", "exec", dont_inherit=True), namespace)
    if target == "api":
        client = TestClient(namespace["app"])
        response = client.post("/greet", json="Ada")
        assert response.status_code == 200
        assert response.json() == {"result": "Hello Ada"}
        default = client.post("/greet")
        assert default.status_code == 200
        assert default.json() == {"result": "Hello world"}
    else:
        result = asyncio.run(namespace["mcp"].call_tool("greet", {"name": "Ada"}))
        assert not result.is_error
        assert result.content[0].text == "Hello Ada"


def test_builtin_typer_conversion_is_not_a_user_callback(tmp_source):
    path = tmp_source("""\
from pathlib import Path
from enum import Enum
import typer
class Color(str, Enum):
    RED = "red"
app = typer.Typer()
@app.command()
def show(path: Path, color: Color):
    typer.echo(f"{path}:{color.value}")
""")
    assert all(
        not p.unsupported_callback for p in intpot.load(path).tools[0].parameters
    )
