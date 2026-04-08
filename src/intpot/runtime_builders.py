"""Build live framework instances from registered tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import typer as _typer

    from intpot.runtime import RegisteredTool


def build_typer_app(name: str, tools: list[RegisteredTool]) -> _typer.Typer:
    """Construct a Typer CLI app from registered tools."""
    import functools

    import typer

    cli_app = typer.Typer(name=name, help=f"{name} — powered by intpot")
    for tool in tools:
        # Wrap so return values are printed — plain functions return values,
        # but Typer commands need explicit output via typer.echo().
        fn = tool.func

        @functools.wraps(fn)
        def _cli_wrapper(*args: object, _fn: object = fn, **kwargs: object) -> None:
            result = _fn(*args, **kwargs)  # type: ignore[operator]
            if result is not None:
                typer.echo(result)

        cli_app.command(name=tool.info.name, help=tool.info.description)(_cli_wrapper)
    return cli_app


def build_fastapi_app(name: str, tools: list[RegisteredTool]) -> object:
    """Construct a FastAPI app from registered tools."""
    try:
        from fastapi import FastAPI
    except ImportError:
        raise ModuleNotFoundError(
            "FastAPI is required for API serving. "
            "Install it with: pip install intpot[api]"
        ) from None

    api_app = FastAPI(title=name)
    for tool in tools:
        route_path = f"/{tool.info.name}"
        method = tool.info.http_method.lower() if tool.info.http_method else "post"
        handler = getattr(api_app, method, api_app.post)
        handler(route_path, summary=tool.info.description)(tool.func)
    return api_app


def build_fastmcp_app(name: str, tools: list[RegisteredTool]) -> object:
    """Construct a FastMCP server from registered tools."""
    try:
        from fastmcp import FastMCP
    except ImportError:
        raise ModuleNotFoundError(
            "FastMCP is required for MCP serving. "
            "Install it with: pip install intpot[mcp]"
        ) from None

    mcp = FastMCP(name)
    for tool in tools:
        mcp.tool(name=tool.info.name, description=tool.info.description)(tool.func)
    return mcp
