"""Extract tools from a FastMCP server instance."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
from collections.abc import Callable, Coroutine, Mapping
from typing import Annotated, Any, cast, get_args, get_origin

from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_return_type_name,
    python_type_name,
)
from intpot.core.inspectors.base import BaseInspector, InspectionError
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def _is_mcp_context(annotation: Any) -> bool:
    """Check if an annotation is the FastMCP Context type."""
    if isinstance(annotation, type):
        return annotation.__name__ == "Context" and "fastmcp" in (
            annotation.__module__ or ""
        )
    return False


def _base_annotation(annotation: Any) -> Any:
    """Return the executable Python type beneath Annotated metadata."""
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return annotation


def _unsupported_registry_error() -> InspectionError:
    return InspectionError(
        "Unsupported FastMCP registry shape: expected "
        "local_provider._list_tools() (FastMCP 3) or "
        "_tool_manager.list_tools()/get_tools() (FastMCP 2). Please install a "
        "supported FastMCP 2.x or 3.x release."
    )


def _run_async(factory: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    """Run a framework coroutine from synchronous or asynchronous callers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


def _call_registry(factory: Callable[[], Any]) -> Any:
    """Call a registry method that may be synchronous or asynchronous."""

    async def invoke() -> Any:
        result = factory()
        if inspect.isawaitable(result):
            return await result
        return result

    return _run_async(invoke)


class MCPInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []

        # FastMCP 3 stores tools via local_provider; FastMCP 2 uses
        # _tool_manager. Match the registries structurally rather than importing
        # generation-specific implementation types.
        provider = getattr(app, "local_provider", None)
        if provider is None:
            manager = getattr(app, "_tool_manager", None)
            list_tools = cast(Any, getattr(manager, "list_tools", None))
            if not callable(list_tools):
                list_tools = cast(Any, getattr(manager, "get_tools", None))
            if not callable(list_tools):
                raise _unsupported_registry_error()
            function_tools: Any = _call_registry(list_tools)
        else:
            list_tools = cast(
                Callable[[], Any] | None, getattr(provider, "_list_tools", None)
            )
            if not callable(list_tools):
                raise _unsupported_registry_error()
            function_tools = _call_registry(list_tools)

        if isinstance(function_tools, Mapping):
            function_tools = function_tools.values()

        for ft in function_tools:
            fn = getattr(ft, "fn", None)
            if fn is None:
                continue

            tool_name = getattr(ft, "name", fn.__name__)
            description = getattr(ft, "description", "") or ""
            if not description and fn.__doc__:
                description = fn.__doc__.strip()

            sig = inspect.signature(fn)
            parameter_schema = getattr(ft, "parameters", {})
            schema_properties = parameter_schema.get("properties", {})
            type_hints: dict[str, Any] = {}
            try:
                type_hints = inspect.get_annotations(fn, eval_str=True)
            except Exception:
                pass

            params: list[ParameterInfo] = []
            for param_name, param in sig.parameters.items():
                annotation = _base_annotation(
                    type_hints.get(param_name, param.annotation)
                )
                if _is_mcp_context(annotation):
                    continue
                type_str = python_type_name(annotation)

                default = _SENTINEL
                if param.default is not inspect.Parameter.empty:
                    default = param.default

                params.append(
                    ParameterInfo(
                        name=param_name,
                        type_annotation=type_str,
                        default=default,
                        description=schema_properties.get(param_name, {}).get(
                            "description", ""
                        )
                        or "",
                    )
                )

            return_annotation = _base_annotation(
                type_hints.get("return", sig.return_annotation)
            )
            return_type = python_return_type_name(return_annotation)

            tools.append(
                ToolInfo(
                    name=tool_name,
                    description=description,
                    parameters=params,
                    return_type=return_type,
                    function_body=extract_function_body(fn),
                    source_imports=extract_source_imports(fn),
                    is_async=asyncio.iscoroutinefunction(fn),
                )
            )

        return tools
