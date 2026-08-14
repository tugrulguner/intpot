"""Extract commands from a Typer app instance."""

from __future__ import annotations

import asyncio
from typing import Any

from intpot.core.inspectors._utils import extract_function_body, extract_source_imports
from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo

# Typer vendors its own copy of click (`typer._click`), so a Typer app's objects
# are not instances of anything in the standalone `click` package and its
# parameter types are not click's singletons. Everything here is therefore
# matched structurally rather than by identity or isinstance — see #77.
_PARAM_TYPE_NAMES = {
    # click's own vocabulary
    "text": "str",
    "integer": "int",
    "float": "float",
    "boolean": "bool",
    # typer's vendored click reports Python names directly
    "str": "str",
    "int": "int",
    "bool": "bool",
    "string": "str",
}


def _click_type_to_str(param_type: Any) -> str:
    """Map a Click/Typer parameter type to a Python type name."""
    name = getattr(param_type, "name", None)
    if isinstance(name, str) and name.lower() in _PARAM_TYPE_NAMES:
        return _PARAM_TYPE_NAMES[name.lower()]
    # Fall back to the class name: IntParamType -> "int".
    cls_name = type(param_type).__name__.removesuffix("ParamType").lower()
    return _PARAM_TYPE_NAMES.get(cls_name, "str")


def _child_commands(obj: Any) -> dict[str, Any] | None:
    """The sub-commands of a group, or None if this is a leaf command."""
    commands = getattr(obj, "commands", None)
    return commands if isinstance(commands, dict) else None


class CLIInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []

        # Get the underlying Click group
        click_group = None
        try:
            # Typer creates a Click group via its __call__ or internal method
            click_group = app  # Try using it directly first
            if hasattr(app, "_get_command"):
                click_group = app._get_command()
            elif hasattr(app, "registered_commands"):
                # Build the click group by invoking typer internals
                import typer.main

                click_group = typer.main.get_group(app)
        except Exception:
            pass

        if click_group is None:
            return tools

        self._extract_commands(click_group, tools, prefix="")
        return tools

    def _extract_commands(
        self,
        group: Any,
        tools: list[ToolInfo],
        prefix: str = "",
    ) -> None:
        """Recursively extract commands from Click/Typer groups."""
        commands = _child_commands(group)
        if commands is None:
            # A single command rather than a group.
            commands = {getattr(group, "name", None) or "main": group}

        for cmd_name, cmd in commands.items():
            if cmd_name is None:
                continue

            full_name = f"{prefix}{cmd_name}".replace("-", "_")

            # Recurse into sub-groups
            if _child_commands(cmd) is not None:
                self._extract_commands(cmd, tools, prefix=f"{full_name}_")
                continue

            self._extract_single_command(cmd, full_name, tools)

    def _extract_single_command(
        self,
        cmd: Any,
        name: str,
        tools: list[ToolInfo],
    ) -> None:
        """Extract a single Click command into a ToolInfo."""
        description = cmd.help or ""

        params: list[ParameterInfo] = []
        for param in cmd.params:
            if param.name is None or param.name == "help":
                continue

            type_str = _click_type_to_str(param.type)

            # Check if parameter is required via Click's own flag
            default = _SENTINEL
            if not getattr(param, "required", False):
                default = param.default

            desc = ""
            if hasattr(param, "help") and param.help:
                desc = param.help

            params.append(
                ParameterInfo(
                    name=param.name,
                    type_annotation=type_str,
                    default=default,
                    description=desc,
                )
            )

        # Extract function body and async status from the callback
        callback = cmd.callback
        fn_body = extract_function_body(callback) if callback else None
        src_imports = extract_source_imports(callback) if callback else []
        is_async = asyncio.iscoroutinefunction(callback) if callback else False

        tools.append(
            ToolInfo(
                name=name,
                description=description,
                parameters=params,
                return_type="str",
                function_body=fn_body,
                is_async=is_async,
                source_imports=src_imports,
            )
        )
