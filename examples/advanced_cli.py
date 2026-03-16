"""Advanced Typer CLI — task manager with multiple commands and types."""

import json

import typer

app = typer.Typer()


@app.command()
def create(
    title: str = typer.Argument(..., help="Task title"),
    priority: int = typer.Option(3, help="Priority level 1-5"),
    tags: str = typer.Option("", help="Comma-separated tags"),
) -> None:
    """Create a new task with optional priority and tags."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    task = {"title": title, "priority": priority, "tags": tag_list}
    typer.echo(json.dumps(task, indent=2))


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, help="Max results to return"),
    include_done: bool = typer.Option(False, help="Include completed tasks"),
) -> None:
    """Search tasks by title or tag."""
    results = [
        {"title": f"Match: {query}", "done": False},
        {"title": f"Another: {query}", "done": True},
    ]
    if not include_done:
        results = [r for r in results if not r["done"]]
    typer.echo(json.dumps(results[:limit], indent=2))


@app.command()
def stats() -> None:
    """Show task statistics."""
    summary = {"total": 42, "done": 15, "pending": 27}
    typer.echo(json.dumps(summary))


if __name__ == "__main__":
    app()
