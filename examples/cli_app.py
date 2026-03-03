"""Example Typer CLI app for testing conversions."""

import typer

app = typer.Typer()


@app.command()
def add(
    a: int = typer.Argument(..., help="First number"),
    b: int = typer.Argument(..., help="Second number"),
) -> None:
    """Add two numbers together."""
    typer.echo(a + b)


@app.command()
def greet(
    name: str = typer.Argument(..., help="Name to greet"),
    greeting: str = typer.Option("Hello", help="Greeting to use"),
) -> None:
    """Greet someone by name."""
    typer.echo(f"{greeting}, {name}!")
