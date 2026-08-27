"""Public CLI compatibility tests for the declared Typer floor."""

from pathlib import Path

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_public_version_command_starts() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0, result.exception
    assert result.stdout.startswith("intpot ")


def test_public_cli_converts_shipped_boolean_option_example() -> None:
    source = Path(__file__).parents[2] / "examples" / "advanced_cli.py"

    result = runner.invoke(app, ["to", "mcp", str(source)])

    assert result.exit_code == 0, result.exception
    compile(result.stdout, "<advanced_cli_to_mcp>", "exec")
    assert "def search(" in result.stdout
    assert "include_done: bool = False" in result.stdout
