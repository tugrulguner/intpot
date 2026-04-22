"""Runtime framework: define tools once, serve as CLI, API, or MCP."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_type_name,
)
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


@dataclass
class RegisteredTool:
    """A function registered via @app.tool(), bundled with its metadata."""

    func: Callable[..., Any]
    info: ToolInfo


class App:
    """Universal app: register tools once, serve as CLI, API, or MCP.

    Example::

        from intpot import App

        app = App("my-app")

        @app.tool()
        def greet(name: str, greeting: str = "Hello") -> str:
            \"\"\"Greet someone.\"\"\"
            return f"{greeting}, {name}!"

        app.serve(mode="cli")
    """

    def __init__(self, name: str = "intpot-app") -> None:
        self.name = name
        self._tools: list[RegisteredTool] = []

    def __repr__(self) -> str:
        count = len(self._tools)
        return f"App({self.name!r}, tools={count})"

    def tool(
        self, *, name: str | None = None, description: str | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a function as a tool.

        Args:
            name: Override the tool name (defaults to function name).
            description: Override the tool description (defaults to docstring).
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            info = _build_tool_info(
                func, name_override=name, description_override=description
            )
            self._tools.append(RegisteredTool(func=func, info=info))
            return func

        return decorator

    @property
    def tools(self) -> list[ToolInfo]:
        """Return ToolInfo list for all registered tools."""
        return [t.info for t in self._tools]

    def eject(self, target: str) -> str:
        """Generate standalone code for the given target framework.

        Args:
            target: One of "cli", "mcp", "api".

        Returns:
            Generated Python source code as a string.
        """
        generators = {
            "cli": "intpot.core.generators.cli.CLIGenerator",
            "mcp": "intpot.core.generators.mcp.MCPGenerator",
            "api": "intpot.core.generators.api.APIGenerator",
        }
        if target not in generators:
            raise ValueError(f"Unknown target '{target}', expected: cli, mcp, api")

        # Lazy import to avoid pulling in all generators at import time
        module_path, class_name = generators[target].rsplit(".", 1)
        import importlib

        mod = importlib.import_module(module_path)
        generator_cls = getattr(mod, class_name)
        return generator_cls().generate(self.tools)

    def serve(self, mode: str, *, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Serve the registered tools in the specified mode.

        Args:
            mode: One of "cli", "api", "mcp".
            host: Host for API mode (default "0.0.0.0").
            port: Port for API mode (default 8000).
        """
        if not self._tools:
            raise RuntimeError("No tools registered. Use @app.tool() to add tools.")

        if mode == "cli":
            self._serve_cli()
        elif mode == "api":
            self._serve_api(host, port)
        elif mode == "mcp":
            self._serve_mcp()
        else:
            raise ValueError(f"Unknown mode '{mode}', expected: cli, api, mcp")

    def _serve_cli(self) -> None:
        from intpot.runtime_builders import build_typer_app

        cli_app = build_typer_app(self.name, self._tools)
        cli_app()

    def _serve_api(self, host: str, port: int) -> None:
        from intpot.runtime_builders import build_fastapi_app

        try:
            import uvicorn
        except ImportError:
            raise ModuleNotFoundError(
                "uvicorn is required for API serving. Install it with: pip install intpot[api]"
            ) from None

        api_app = build_fastapi_app(self.name, self._tools)
        uvicorn.run(api_app, host=host, port=port)  # type: ignore[arg-type]

    def _serve_mcp(self) -> None:
        from intpot.runtime_builders import build_fastmcp_app

        mcp_app = build_fastmcp_app(self.name, self._tools)
        mcp_app.run()


def _build_tool_info(
    func: Callable[..., Any],
    *,
    name_override: str | None = None,
    description_override: str | None = None,
) -> ToolInfo:
    """Build a ToolInfo from a plain Python function."""
    tool_name = name_override or func.__name__
    description = (
        description_override
        if description_override is not None
        else (inspect.getdoc(func) or "")
    )
    is_async = asyncio.iscoroutinefunction(func)

    # Extract parameters from signature + type hints
    sig = inspect.signature(func)
    try:
        hints = _safe_get_type_hints(func)
    except Exception:
        hints = {}

    parameters: list[ParameterInfo] = []
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        # Type annotation
        if param_name in hints:
            type_str = python_type_name(hints[param_name])
        elif param.annotation is not inspect.Parameter.empty:
            type_str = python_type_name(param.annotation)
        else:
            type_str = "str"

        # Default value
        if param.default is inspect.Parameter.empty:
            default: Any = _SENTINEL
        else:
            default = param.default

        parameters.append(
            ParameterInfo(
                name=param_name,
                type_annotation=type_str,
                default=default,
            )
        )

    # Return type
    return_hint = hints.get("return", sig.return_annotation)
    if return_hint is inspect.Parameter.empty or return_hint is None:
        return_type = "str"
    else:
        return_type = python_type_name(return_hint)

    # Extract function body and imports for eject
    function_body = extract_function_body(func)
    source_imports = extract_source_imports(func)

    return ToolInfo(
        name=tool_name,
        description=description,
        parameters=parameters,
        return_type=return_type,
        is_async=is_async,
        function_body=function_body,
        source_imports=source_imports,
    )


def _safe_get_type_hints(func: Callable[..., Any]) -> dict[str, Any]:
    """Get type hints, falling back gracefully."""
    try:
        return inspect.get_annotations(func, eval_str=True)
    except Exception:
        return inspect.get_annotations(func, eval_str=False)
