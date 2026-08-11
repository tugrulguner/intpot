"""intpot CLI entry point."""

import typer

from intpot.commands.add_skills import add_skills
from intpot.commands.eject import eject_command
from intpot.commands.init import init_command
from intpot.commands.inspect import inspect_command
from intpot.commands.serve import serve_command
from intpot.commands.to_api import to_api
from intpot.commands.to_cli import to_cli
from intpot.commands.to_mcp import to_mcp


def _version_callback(value: bool) -> None:
    if value:
        from intpot import __version__

        typer.echo(f"intpot {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="intpot",
    help=(
        "Define Python tools once and serve them as a Typer CLI, FastAPI app, "
        "or FastMCP server — or convert existing apps between all three."
    ),
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
    """Serve Python tools as a CLI, API, or MCP server — or convert between them."""


to_app = typer.Typer(
    name="to",
    help="Convert a source app to a different interface type.",
    no_args_is_help=True,
)

add_app = typer.Typer(
    name="add",
    help="Install extras into the current project.",
    no_args_is_help=True,
)

app.command("init")(init_command)
app.command("inspect")(inspect_command)
app.command(
    "serve",
    # Arguments intpot does not recognise belong to the served app, not to us.
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)(serve_command)
app.command("eject")(eject_command)
to_app.command("cli")(to_cli)
to_app.command("mcp")(to_mcp)
to_app.command("api")(to_api)
add_app.command("skills")(add_skills)
app.add_typer(to_app, name="to")
app.add_typer(add_app, name="add")
