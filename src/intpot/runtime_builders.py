"""Build live framework instances from registered tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from intpot.core.models import ParamSource, ToolInfo

if TYPE_CHECKING:
    import typer as _typer

    from intpot.runtime import RegisteredTool

_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
)


def build_typer_app(name: str, tools: list[RegisteredTool]) -> _typer.Typer:
    """Construct a Typer CLI app from registered tools."""
    import asyncio
    import functools
    import inspect

    import typer

    cli_app = typer.Typer(name=name, help=f"{name} — powered by intpot")
    for tool in tools:
        # Wrap so return values are printed — plain functions return values,
        # but Typer commands need explicit output via typer.echo().
        fn = tool.func

        @functools.wraps(fn)
        def _cli_wrapper(*args: object, _fn: object = fn, **kwargs: object) -> None:
            result = _fn(*args, **kwargs)  # type: ignore[operator]
            if inspect.iscoroutine(result):
                result = asyncio.run(result)
            if result is not None:
                typer.echo(result)

        cli_app.command(name=tool.info.name, help=tool.info.description)(_cli_wrapper)
    return cli_app


def _fastapi_endpoint(func: Callable[..., Any], info: ToolInfo) -> Callable[..., Any]:
    """Wrap a tool so FastAPI reads its parameters from the declared sources.

    Registering a plain function makes FastAPI infer a location per parameter,
    and scalars become query parameters. Generated code declares the same
    parameters via ``Body``/``Query``/``Header``/``Path`` from
    ``ParameterInfo.param_source``, so serving and ejecting would otherwise
    expose two different HTTP interfaces for one app.
    """
    import functools
    import inspect
    from typing import get_type_hints

    from fastapi import Body, Header, Path, Query

    markers = {
        ParamSource.body: Body,
        ParamSource.query: Query,
        ParamSource.header: Header,
        ParamSource.path: Path,
    }
    sources = {p.name: p.param_source for p in info.parameters}

    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    signature = inspect.signature(func)
    parameters = []
    for param_name, param in signature.parameters.items():
        marker = markers[sources.get(param_name) or ParamSource.body]
        declared = (
            marker(...)
            if param.default is inspect.Parameter.empty
            else marker(param.default)
        )
        parameters.append(
            param.replace(
                default=declared,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=hints.get(param_name, param.annotation),
            )
        )

    endpoint: Callable[..., Any]
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def _async_endpoint(**kwargs: Any) -> Any:
            return await func(**kwargs)

        endpoint = _async_endpoint
    else:

        @functools.wraps(func)
        def _sync_endpoint(**kwargs: Any) -> Any:
            return func(**kwargs)

        endpoint = _sync_endpoint

    endpoint.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=parameters,
        return_annotation=hints.get("return", signature.return_annotation),
    )
    return endpoint


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
        route_path = tool.info.route_path or f"/{tool.info.name}"
        method = (tool.info.http_method or "POST").upper()
        if method not in _HTTP_METHODS:
            method = "POST"
        api_app.add_api_route(
            route_path,
            _fastapi_endpoint(tool.func, tool.info),
            methods=[method],
            summary=tool.info.description,
        )
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
