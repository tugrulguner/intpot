from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from typer.testing import CliRunner

import intpot
from intpot.core.models import ParameterInfo, ParameterSchema


@pytest.mark.parametrize("model", [ParameterInfo, ParameterSchema])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum": True},
        {"maximum": float("inf")},
        {"minimum": float("nan")},
        {"minimum": "1"},
        {"minimum": 5, "maximum": 1},
        {"minimum": 1, "default": 0},
    ],
)
def test_invalid_range_metadata_is_rejected(model, kwargs):
    with pytest.raises(ValueError):
        model("quantity", "int", **kwargs)


def test_one_sided_argument_and_float_default_survive_projection(tmp_path, monkeypatch):
    path = tmp_path / "arguments.py"
    path.write_text(
        "import typer\napp=typer.Typer()\n@app.command()\ndef quote(quantity: int = typer.Argument(..., min=1), rate: float = typer.Option(2, min=0.5)):\n    typer.echo(str(quantity * rate))\n"
    )
    loaded = intpot.load(path)
    assert CliRunner().invoke(loaded.app, ["3"]).stdout.strip() == "6.0"
    assert loaded.schema.tools[0].parameters[1].default == 2.0
    ns = {}
    exec(loaded.to_api(), ns)
    client = TestClient(ns["app"])
    assert client.post("/quote", json={"quantity": 3}).json() == {"result": "6.0"}
    assert client.post("/quote", json={"quantity": 0}).status_code == 422
    import typer.main

    from intpot.core.inspectors.cli import CLIInspector

    def fail_group(_):
        raise ValueError("force registered fallback")

    monkeypatch.setattr(typer.main, "get_group", fail_group)
    parameters = CLIInspector().inspect(loaded.app)[0].parameters
    assert parameters[0].minimum == 1 and parameters[1].minimum == 0.5
    assert parameters[1].default == 2.0


def test_range_refusal_cli_json_and_callback_precedence(tmp_path):
    from intpot.cli import app

    path = tmp_path / "callbacks.py"
    path.write_text(
        "import typer\napp=typer.Typer()\ndef validate(value):\n    return value\n@app.command()\ndef quote(quantity: int = typer.Option(..., min=1, clamp=True, callback=validate)):\n    typer.echo(str(quantity))\n"
    )
    loaded = intpot.load(path)
    with pytest.raises(intpot.UnsupportedCLIParameterCallbackError):
        loaded.to_api()
    result = CliRunner().invoke(app, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["assessment"] == loaded.assess()
    result = CliRunner().invoke(app, ["to", "api", str(path)])
    assert result.exit_code == 1 and "callback" in result.output.lower()


def test_exclusive_and_custom_range_types_are_not_silently_narrowed():
    from click import IntRange

    from intpot.core.numeric_ranges import cli_numeric_range

    assert cli_numeric_range(IntRange(min=1, min_open=True), constructed=True) == {
        "unsupported_numeric_range": True
    }

    class CustomRange(IntRange):
        pass

    assert cli_numeric_range(CustomRange(min=1), constructed=True) == {
        "unsupported_numeric_range": True
    }


def test_invalid_numeric_default_does_not_silently_bypass_validation(tmp_path):
    path = tmp_path / "invalid_default.py"
    path.write_text(
        "import typer\napp=typer.Typer()\n@app.command()\ndef quote(quantity: int = typer.Option(0, min=1)):\n    typer.echo(str(quantity))\n"
    )
    loaded = intpot.load(path)
    assert CliRunner().invoke(loaded.app, []).exit_code == 2
    assert loaded.schema.tools[0].parameters[0].unsupported_numeric_range
    with pytest.raises(intpot.UnsupportedCLINumericRangeError):
        loaded.to_api()


@pytest.mark.parametrize("clamp", [True])
def test_clamping_is_inspectable_but_refuses_before_scaffold_writes(tmp_path, clamp):
    path = tmp_path / "clamping.py"
    path.write_text(
        f"import typer\napp=typer.Typer()\n@app.command()\ndef quote(quantity: int = typer.Option(..., min=1, max=10, clamp={clamp})):\n    typer.echo(str(quantity))\n"
    )
    loaded = intpot.load(path)
    assert CliRunner().invoke(loaded.app, ["--quantity", "0"]).stdout.strip() == "1"
    report = loaded.assess()
    assert len(report["diagnostics"]) == 2
    assert all(
        item["code"] == "unsupported_cli_numeric_range"
        for item in report["diagnostics"]
    )
    for target in ("api", "mcp"):
        for scaffold in (False, True):
            output = tmp_path / f"{target}-{scaffold}" / "app.py"
            with pytest.raises(intpot.UnsupportedCLINumericRangeError):
                loaded.write(output, target, allow_scaffold=scaffold)
            assert not output.parent.exists()


def test_numeric_bounds_are_immutable_and_survive_adapters():
    parameter = ParameterSchema.from_info(
        ParameterInfo("quantity", "int", minimum=1, maximum=10)
    )
    assert parameter.minimum == 1 and parameter.maximum == 10
    assert parameter == ParameterSchema.from_info(parameter.to_info())
    assert hash(parameter) == hash(ParameterSchema.from_info(parameter.to_info()))
    assert parameter != replace(parameter, maximum=11)
    assert json.loads(json.dumps(parameter.to_dict()))["minimum"] == 1
    assert "minimum" not in ParameterSchema("plain").to_dict()


@pytest.mark.parametrize(
    "type_name,minimum,maximum,valid,bad",
    [("int", 1, 10, 3, 0), ("float", 0.5, 2.5, 1.25, 3.0)],
)
def test_public_cli_numeric_ranges_reach_native_generated_consumers(
    tmp_path, type_name, minimum, maximum, valid, bad
):
    path = tmp_path / "bounded.py"
    path.write_text(
        f"import typer\napp=typer.Typer()\n@app.command()\ndef quote(quantity: {type_name} = typer.Option(..., min={minimum}, max={maximum})):\n    typer.echo(str(quantity))\n"
    )
    loaded = intpot.load(path)
    assert CliRunner().invoke(loaded.app, ["--quantity", str(valid)]).exit_code == 0
    assert CliRunner().invoke(loaded.app, ["--quantity", str(bad)]).exit_code == 2
    parameter = loaded.schema.tools[0].parameters[0]
    assert parameter.type_annotation == type_name
    assert parameter.minimum == minimum and parameter.maximum == maximum
    ns = {}
    exec(loaded.to_api(), ns)
    client = TestClient(ns["app"])
    assert client.post("/quote", json=valid).status_code == 200
    assert client.post("/quote", json=bad).status_code == 422
    ns = {}
    exec(loaded.to_mcp(), ns)

    async def check():
        async with Client(ns["mcp"]) as mcp:
            tools = await mcp.list_tools()
            tool_schema = (
                getattr(tools[0], "input_schema", None) or tools[0].inputSchema
            )
            field = tool_schema["properties"]["quantity"]
            assert field["minimum"] == minimum and field["maximum"] == maximum
            assert not (await mcp.call_tool("quote", {"quantity": valid})).is_error
            assert (
                await mcp.call_tool("quote", {"quantity": bad}, raise_on_error=False)
            ).is_error

    asyncio.run(check())
