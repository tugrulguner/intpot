"""Public CLI compatibility tests for the declared Typer floor."""

import asyncio
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


def test_generated_nullable_string_enum_uses_floor_compatible_annotation(
    tmp_path, monkeypatch
):
    import sys

    import intpot
    from intpot.core.detector import detect_source
    from intpot.core.generators.cli import CLIGenerator

    package = tmp_path / "floor_enum_compat"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "modes.py").write_text(
        "from enum import Enum\nclass Mode(str, Enum):\n FAST='fast'\n SAFE='safe'\n"
    )
    source = package / "app.py"
    effect = tmp_path / "body-executed"
    source.write_text(
        "from pathlib import Path\nfrom typing import Optional\nimport typer\nfrom .modes import Mode\napp=typer.Typer()\n@app.command()\ndef run(mode: Mode, maybe: Optional[Mode]=None):\n"
        f" Path({str(effect)!r}).write_text('executed')\n"
        " typer.echo(mode.value + ':' + ('none' if maybe is None else maybe.value))\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        loaded = intpot.load(source)
        namespace: dict[str, Any] = {"__name__": "floor_enum_generated"}
        exec(CLIGenerator().generate(loaded.schema), namespace)
        result = runner.invoke(namespace["app"], ["fast"])
        assert result.exit_code == 0, result.exception
        assert result.stdout.strip() == "fast:none"
        assert effect.read_text() == "executed"
        effect.unlink()
        _, original = detect_source(source)
        source_invalid = runner.invoke(original, ["invalid"])
        assert source_invalid.exit_code != 0
        assert not effect.exists()
        generated_invalid = runner.invoke(namespace["app"], ["invalid"])
        assert generated_invalid.exit_code == source_invalid.exit_code
        assert not effect.exists()
        if source_invalid.exit_code != 2:
            # Legacy Typer/Click can fail while formatting the validation error.
            # Preserve that source-only failure rather than masking it with a pin.
            assert isinstance(source_invalid.exception, TypeError)
            assert "make_metavar" in str(source_invalid.exception)
            assert type(generated_invalid.exception) is type(source_invalid.exception)
            assert str(generated_invalid.exception) == str(source_invalid.exception)
    finally:
        for key in tuple(sys.modules):
            if key == package.name or key.startswith(package.name + "."):
                del sys.modules[key]


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
    namespace: dict[str, Any] = {}
    exec(compile(result.stdout, "<annotated_cli_to_mcp>", "exec"), namespace)
    call = asyncio.run(
        namespace["mcp"].call_tool(
            "admin_search", {"query": "needle", "include_done": True}
        )
    )
    assert call.is_error is False
    assert call.structured_content == {"result": "needle:True"}


def test_public_cli_tool_selection_works_at_declared_typer_floor(tmp_path) -> None:
    source = tmp_path / "selectable.py"
    source.write_text("""import typer
app = typer.Typer()
def validate(value):
    return value
@app.command()
def mapping() -> None:
    typer.echo("useful")
@app.command()
def blocked(value: str = typer.Option("", callback=validate)) -> None:
    typer.echo(value)
""")
    result = runner.invoke(app, ["to", "mcp", str(source), "--tool", "mapping"])
    assert result.exit_code == 0, result.exception
    namespace: dict[str, Any] = {}
    exec(result.stdout, namespace)
    call = asyncio.run(namespace["mcp"].call_tool("mapping", {}))
    assert call.is_error is False
    assert call.structured_content == {"result": "useful"}
    assert "blocked" not in namespace
