"""Build live framework instances from registered tools."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from intpot.core.models import (
    ParameterInfo,
    ParameterPlacement,
    SourceType,
    ToolInfo,
    deduplicate_identifiers,
    sanitize_identifier,
)
from intpot.core.projections import (
    resolve_cli_aliases,
    resolve_parameter_placement,
    resolve_tool_interface_name,
)

if TYPE_CHECKING:
    import typer as _typer

    from intpot.runtime import RegisteredTool

_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
)


def _parameter_contracts(
    func: Callable[..., Any], info: ToolInfo
) -> dict[str, ParameterInfo]:
    """Map callable names to canonical metadata without assuming equal spelling.

    ``ParameterInfo`` sanitizes and deduplicates names, while the live callable
    retains its original Python signature. Rebuilding that canonical identity
    map keeps colliding source names distinct without relying on metadata order.
    """
    import inspect

    variadic = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    callable_parameters = [
        parameter
        for parameter in inspect.signature(func).parameters.values()
        if parameter.kind not in variadic
    ]
    canonical_names = deduplicate_identifiers(
        [sanitize_identifier(parameter.name) for parameter in callable_parameters]
    )
    contracts_by_name = {parameter.name: parameter for parameter in info.parameters}
    if len(contracts_by_name) != len(info.parameters) or set(canonical_names) != set(
        contracts_by_name
    ):
        raise ValueError(
            f"Tool {info.name!r} callable parameters do not match its parameter contracts"
        )
    return {
        parameter.name: contracts_by_name[canonical_name]
        for parameter, canonical_name in zip(
            callable_parameters, canonical_names, strict=True
        )
    }


def _restore_positional_only(
    func: Callable[..., Any], info: ToolInfo | None = None
) -> Callable[..., Any]:
    """Expose the canonical parameter contract while restoring positional calls."""
    import functools
    import inspect

    signature = inspect.signature(func)
    positional_only = tuple(
        param.name
        for param in signature.parameters.values()
        if param.kind == inspect.Parameter.POSITIONAL_ONLY
    )
    contracts = {} if info is None else _parameter_contracts(func, info)
    canonical_strings = {
        name
        for name, parameter in contracts.items()
        if parameter.type_annotation == "str"
    }
    needs_annotations = any(
        param.annotation is inspect.Parameter.empty and param.name in canonical_strings
        for param in signature.parameters.values()
    )
    if not positional_only and not needs_annotations:
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

    exposed_signature = signature.replace(
        parameters=[
            param.replace(
                kind=(
                    inspect.Parameter.POSITIONAL_OR_KEYWORD
                    if param.kind == inspect.Parameter.POSITIONAL_ONLY
                    else param.kind
                ),
                annotation=(
                    str
                    if param.annotation is inspect.Parameter.empty
                    and param.name in canonical_strings
                    else param.annotation
                ),
            )
            for param in signature.parameters.values()
        ]
    )
    wrapper.__signature__ = exposed_signature  # type: ignore[attr-defined]
    if needs_annotations:
        wrapper.__annotations__ = dict(wrapper.__annotations__)
        for parameter in exposed_signature.parameters.values():
            original = signature.parameters[parameter.name]
            if (
                original.annotation is inspect.Parameter.empty
                and parameter.annotation is not inspect.Parameter.empty
            ):
                wrapper.__annotations__[parameter.name] = parameter.annotation
    return wrapper


def build_typer_app(name: str, tools: list[RegisteredTool]) -> _typer.Typer:
    """Construct a Typer CLI app from registered tools."""
    import asyncio
    import functools
    import inspect

    import typer

    def _command_endpoint(
        func: Callable[..., Any], info: ToolInfo
    ) -> Callable[..., Any]:
        restored = _restore_positional_only(func, info)

        @functools.wraps(restored)
        def endpoint(*args: Any, **kwargs: Any) -> Any:
            return restored(*args, **kwargs)

        signature = inspect.signature(restored)
        contracts = _parameter_contracts(restored, info)
        parameters = []
        for parameter in signature.parameters.values():
            contract = contracts[parameter.name]
            placement = resolve_parameter_placement(contract, SourceType.CLI)
            if placement is ParameterPlacement.CLI_ARGUMENT:
                default = typer.Argument(..., help=contract.description)
            else:
                option_default = ... if contract.required else contract.default
                default = typer.Option(
                    option_default,
                    *resolve_cli_aliases(contract),
                    help=contract.description,
                )
            parameters.append(parameter.replace(default=default))
        endpoint.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=parameters
        )
        return endpoint

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
        wrapped = _echoing(_command_endpoint(tool.func, tool.info))
        cli_app.command(
            name=resolve_tool_interface_name(tool.info, SourceType.CLI),
            help=tool.info.description,
        )(wrapped)
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
        ParameterPlacement.API_BODY: Body,
        ParameterPlacement.API_QUERY: Query,
        ParameterPlacement.API_HEADER: Header,
        ParameterPlacement.API_PATH: Path,
    }
    contracts = _parameter_contracts(func, info)
    canonical_strings = {
        name
        for name, parameter in contracts.items()
        if parameter.type_annotation == "str"
    }

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
        contract = contracts[param_name]
        placement = resolve_parameter_placement(contract, SourceType.API)
        marker = markers[placement]
        marker_kwargs = (
            {"description": contract.description} if contract.description else {}
        )
        if contract.interface_name is not None:
            marker_kwargs["alias"] = contract.interface_name
        declared = (
            marker(..., **marker_kwargs)
            if contract.required
            else marker(contract.default, **marker_kwargs)
        )
        annotation = hints.get(param_name, param.annotation)
        parameters.append(
            param.replace(
                default=declared,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=(
                    str
                    if annotation is inspect.Parameter.empty
                    and param_name in canonical_strings
                    else annotation
                ),
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
        interface_name = resolve_tool_interface_name(tool.info, SourceType.API)
        route_path = tool.info.route_path or f"/{interface_name}"
        method = (tool.info.http_method or "POST").upper()
        if method not in _HTTP_METHODS:
            method = "POST"
        api_app.add_api_route(
            route_path,
            _fastapi_endpoint(tool.func, tool.info),
            methods=[method],
            name=interface_name,
            operation_id=tool.info.operation_id,
            summary=(
                tool.info.route_summary
                if tool.info.route_summary is not None
                else tool.info.description
            ),
            description=(
                tool.info.route_description
                if tool.info.route_description is not None
                else tool.info.description
            ),
            tags=list(tool.info.route_tags) or None,
            deprecated=tool.info.route_deprecated,
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
        mcp.tool(
            name=resolve_tool_interface_name(tool.info, SourceType.MCP),
            description=tool.info.description,
        )(_restore_positional_only(tool.func, tool.info))
    return mcp
