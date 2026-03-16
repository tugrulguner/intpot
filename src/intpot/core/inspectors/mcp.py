"""Extract tools from a FastMCP server instance."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_type_name,
)
from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def _is_mcp_context(annotation: Any) -> bool:
    """Check if an annotation is the FastMCP Context type."""
    if isinstance(annotation, type):
        return annotation.__name__ == "Context" and "fastmcp" in (
            annotation.__module__ or ""
        )
    return False


class MCPInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []

        # FastMCP >=2.0 stores tools via local_provider
        # Use the async _list_tools to get registered FunctionTool objects
        provider = getattr(app, "local_provider", None)
        if provider is None:
            return tools

        try:
            function_tools = asyncio.run(provider._list_tools())
        except RuntimeError:
            # Already in an async context — create a new event loop in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                function_tools = pool.submit(
                    asyncio.run, provider._list_tools()
                ).result()

        for ft in function_tools:
            fn = getattr(ft, "fn", None)
            if fn is None:
                continue

            tool_name = getattr(ft, "name", fn.__name__)
            description = getattr(ft, "description", "") or ""
            if not description and fn.__doc__:
                description = fn.__doc__.strip()

            sig = inspect.signature(fn)
            type_hints: dict[str, Any] = {}
            try:
                type_hints = inspect.get_annotations(fn, eval_str=True)
            except Exception:
                pass

            params: list[ParameterInfo] = []
            for param_name, param in sig.parameters.items():
                annotation = type_hints.get(param_name, param.annotation)
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
                        description="",
                    )
                )

            return_annotation = type_hints.get("return", sig.return_annotation)
            return_type = python_type_name(return_annotation)

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
