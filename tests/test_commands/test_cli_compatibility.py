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


def test_public_cli_converts_annotated_parameters_in_named_sub_app(tmp_path) -> None:
    source = tmp_path / "annotated_cli.py"
    source.write_text(
        """from typing import Annotated

import typer

app = typer.Typer()


def build_admin() -> typer.Typer:
    admin = typer.Typer(name="admin")

    @admin.command()
    def search(
        query: Annotated[str, typer.Argument(help="Search query")],
        include_done: Annotated[bool, typer.Option(help="Include completed tasks")] = False,
    ) -> str:
        return f"{query}:{include_done}"

    return admin


app.add_typer(build_admin())
"""
    )

    result = runner.invoke(app, ["to", "mcp", str(source)])

    assert result.exit_code == 0, result.exception
    compile(result.stdout, "<annotated_cli_to_mcp>", "exec")
    assert "def admin_search(" in result.stdout
    assert "query: str" in result.stdout
    assert "include_done: bool = False" in result.stdout
