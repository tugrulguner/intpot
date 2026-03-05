"""intpot CLI entry point."""

import typer

from intpot.commands.init import init_command
from intpot.commands.to_api import to_api
from intpot.commands.to_cli import to_cli
from intpot.commands.to_mcp import to_mcp


def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version

        typer.echo(f"intpot {version('intpot')}")
        raise typer.Exit()


app = typer.Typer(
    name="intpot",
    help="Universal converter between CLI (Typer), MCP (FastMCP), and API (FastAPI) interfaces.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Universal converter between CLI, MCP, and API interfaces."""


to_app = typer.Typer(
    name="to",
    help="Convert a source app to a different interface type.",
    no_args_is_help=True,
)

app.command("init")(init_command)
to_app.command("cli")(to_cli)
to_app.command("mcp")(to_mcp)
to_app.command("api")(to_api)
app.add_typer(to_app, name="to")
