from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client
from typer.testing import CliRunner

import intpot


def test_terminal_echo_does_not_write_explicitly_declared_globals():
    import textwrap

    from intpot.core.models import SourceType, ToolInfo
    from intpot.core.transforms import transform_tools

    tool = ToolInfo(
        "quote",
        function_body="global _intpot_echo_builtins, _intpot_echo_value\ntyper.echo(75)",
    )
    converted = transform_tools([tool], SourceType.CLI, SourceType.MCP)[0]
    namespace: dict[str, Any] = {
        "_intpot_echo_builtins": "untouched",
        "_intpot_echo_value": "untouched",
    }
    exec(
        "def quote():\n" + textwrap.indent(converted.function_body or "", "    "),
        namespace,
    )
    assert namespace["quote"]() == "75"
    assert (
        namespace["_intpot_echo_builtins"]
        == namespace["_intpot_echo_value"]
        == "untouched"
    )


def test_terminal_numeric_echo_matches_cli_through_native_mcp(tmp_path):
    source = tmp_path / "numeric.py"
    source.write_text(
        "import typer\napp = typer.Typer()\n@app.command()\ndef quote(quantity: int = typer.Option(..., min=1, max=10)):\n    total = quantity * 25\n    typer.echo(total)\n"
    )
    loaded = intpot.load(source)
    original = CliRunner().invoke(loaded.app, ["--quantity", "3"])
    assert original.exit_code == 0
    namespace = {}
    exec(loaded.to_mcp(), namespace)

    async def check():
        async with Client(namespace["mcp"]) as client:
            result = await client.call_tool("quote", {"quantity": 3})
            assert result.content[0].text == original.stdout.removesuffix("\n")

    asyncio.run(check())


@pytest.mark.parametrize(
    "expression", ["0", "-5", "1.25", "True", "None", "'hello'", "''"]
)
def test_plain_terminal_echo_text_is_consistent_for_scalar_values(tmp_path, expression):
    source = tmp_path / "scalars.py"
    source.write_text(
        f"import typer\napp = typer.Typer()\n@app.command()\ndef quote():\n    typer.echo({expression})\n"
    )
    loaded = intpot.load(source)
    original = CliRunner().invoke(loaded.app, [])
    assert original.exit_code == 0
    namespace = {}
    exec(loaded.to_mcp(), namespace)

    async def check():
        async with Client(namespace["mcp"]) as client:
            result = await client.call_tool("quote", {})
            assert "".join(
                item.text for item in result.content
            ) == original.stdout.removesuffix("\n")

    asyncio.run(check())


def test_terminal_echo_reserves_original_parameter_names_and_builtin_shadowing(
    tmp_path,
):
    source = tmp_path / "collisions.py"
    source.write_text(
        "import typer\napp = typer.Typer()\n@app.command()\ndef quote(str: int = 3, _intpot_echo_value: int = 4, _intpot_echo_builtins: int = 5):\n    typer.echo(str + _intpot_echo_value + _intpot_echo_builtins)\n"
    )
    loaded = intpot.load(source)
    original = CliRunner().invoke(loaded.app, [])
    assert original.exit_code == 0
    namespace = {}
    exec(loaded.to_mcp(), namespace)

    async def check():
        async with Client(namespace["mcp"]) as client:
            result = await client.call_tool("quote", {})
            assert result.content[0].text == original.stdout.removesuffix("\n")

    asyncio.run(check())


def test_terminal_echo_expression_runs_once_with_real_receipt_side_effect(tmp_path):
    source = tmp_path / "effects.py"
    source.write_text(
        "from pathlib import Path\nimport typer\napp = typer.Typer()\ndef total(receipt: str) -> int:\n    path = Path(receipt)\n    path.write_text(path.read_text() + 'x')\n    return 75\n@app.command()\ndef quote(receipt: str):\n    typer.echo(total(receipt))\n"
    )
    receipt = tmp_path / "receipt.txt"
    receipt.write_text("")
    loaded = intpot.load(source)
    original = CliRunner().invoke(loaded.app, [str(receipt)])
    assert original.exit_code == 0 and receipt.read_text() == "x"
    receipt.write_text("")
    namespace = {}
    exec(loaded.to_mcp(), namespace)

    async def check():
        async with Client(namespace["mcp"]) as client:
            result = await client.call_tool("quote", {"receipt": str(receipt)})
            assert result.content[0].text == original.stdout.removesuffix("\n")
            assert receipt.read_text() == "x"

    asyncio.run(check())
