"""Tests for runtime framework builders."""

from __future__ import annotations

from intpot.runtime import App, RegisteredTool


def _make_tools() -> tuple[App, list[RegisteredTool]]:
    """Create a test app with two tools and return it with its internal tools."""
    app = App("test-app")

    @app.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @app.tool()
    def greet(name: str, greeting: str = "Hello") -> str:
        """Greet someone."""
        return f"{greeting}, {name}!"

    return app, app._tools


def test_build_typer_app():
    from typer.main import get_group

    from intpot.runtime_builders import build_typer_app

    _, tools = _make_tools()
    cli_app = build_typer_app("test", tools)

    # Verify commands are registered via Click group
    group = get_group(cli_app)
    command_names = list(group.commands.keys())
    assert "add" in command_names
    assert "greet" in command_names


def test_build_fastapi_app():
    from intpot.runtime_builders import build_fastapi_app

    _, tools = _make_tools()
    api_app = build_fastapi_app("test", tools)

    # Verify routes are registered
    route_paths = [r.path for r in api_app.routes if hasattr(r, "methods")]
    assert "/add" in route_paths
    assert "/greet" in route_paths


def test_build_fastmcp_app():
    from intpot.runtime_builders import build_fastmcp_app

    _, tools = _make_tools()
    mcp_app = build_fastmcp_app("test", tools)

    # FastMCP stores tools internally — check the name
    assert mcp_app.name == "test"
