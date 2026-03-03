"""{{project_name}} - Typer CLI app."""

import typer

app = typer.Typer()


@app.command()
def hello(name: str = typer.Argument("world", help="Name to greet")) -> None:
    """Say hello."""
    typer.echo(f"Hello, {name}!")


if __name__ == "__main__":
    app()
