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


def _restore_positional_only(func: Callable[..., Any]) -> Callable[..., Any]:
    """Expose positional-only parameters by name, then restore them on invocation."""
    import functools
    import inspect

    signature = inspect.signature(func)
    positional_only = tuple(
        param.name
        for param in signature.parameters.values()
        if param.kind == inspect.Parameter.POSITIONAL_ONLY
    )
    if not positional_only:
        return func

    def call_arguments(
        args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        remaining = dict(kwargs)
        restored = tuple(
            remaining.pop(name) for name in positional_only if name in remaining
        )
        return args + restored, remaining

    wrapper: Callable[..., Any]
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            restored, remaining = call_arguments(args, kwargs)
            return await func(*restored, **remaining)

        wrapper = _async_wrapper
    else:

        @functools.wraps(func)
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            restored, remaining = call_arguments(args, kwargs)
            return func(*restored, **remaining)

        wrapper = _sync_wrapper

    wrapper.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=[
            param.replace(kind=inspect.Parameter.POSITIONAL_OR_KEYWORD)
            if param.kind == inspect.Parameter.POSITIONAL_ONLY
            else param
            for param in signature.parameters.values()
        ]
    )
    return wrapper


def build_typer_app(name: str, tools: list[RegisteredTool]) -> _typer.Typer:
    """Construct a Typer CLI app from registered tools."""
    import asyncio
    import functools
    import inspect

    import typer

    def _echoing(fn: Callable[..., Any]) -> Callable[..., None]:
        """Print what the tool returns; Typer discards return values.

        `fn` is bound by closure rather than as a default argument. As a
        default it sat in the wrapper's own signature, so a tool with a
        parameter of that name overrode it and the wrapper tried to call the
        user's value: `TypeError: 'str' object is not callable`.
        """

        @functools.wraps(fn)
        def _cli_wrapper(*args: object, **kwargs: object) -> None:
            result = fn(*args, **kwargs)
            if inspect.iscoroutine(result):
                result = asyncio.run(result)
            if result is not None:
                typer.echo(result)

        return _cli_wrapper

    cli_app = typer.Typer(name=name, help=f"{name} — powered by intpot")
    for tool in tools:
        wrapped = _echoing(_restore_positional_only(tool.func))
        cli_app.command(name=tool.info.name, help=tool.info.description)(wrapped)
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

    variadic = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)

    signature = inspect.signature(func)
    positional_only = tuple(
        param.name
        for param in signature.parameters.values()
        if param.kind == inspect.Parameter.POSITIONAL_ONLY
    )

    def call_arguments(
        kwargs: dict[str, Any],
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Restore the original callable's positional-only arguments."""
        remaining = dict(kwargs)
        args = tuple(remaining.pop(name) for name in positional_only)
        return args, remaining

    parameters = []
    for param_name, param in signature.parameters.items():
        if param.kind in variadic:
            # *args / **kwargs cannot be expressed as HTTP parameters. Leaving
            # them out means the wrapper simply never passes them, which is
            # what an empty tuple and dict amount to anyway; rewriting them to
            # KEYWORD_ONLY produced a signature FastAPI could not serve.
            continue
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
            args, remaining = call_arguments(kwargs)
            return await func(*args, **remaining)

        endpoint = _async_endpoint
    else:

        @functools.wraps(func)
        def _sync_endpoint(**kwargs: Any) -> Any:
            args, remaining = call_arguments(kwargs)
            return func(*args, **remaining)

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
        mcp.tool(name=tool.info.name, description=tool.info.description)(
            _restore_positional_only(tool.func)
        )
    return mcp
