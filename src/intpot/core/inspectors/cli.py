"""Extract commands from a Typer app instance."""

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
            registered = getattr(app, "registered_commands", None)
            if isinstance(registered, list):
                self._extract_registered_app(app, tools)
                return tools

        if click_group is None:
            return tools

        self._extract_commands(click_group, tools, prefix="")
        return tools

    def _extract_registered_app(
        self,
        app: Any,
        tools: list[ToolInfo],
        prefix: str = "",
        seen: set[int] | None = None,
    ) -> None:
        """Inspect Typer callbacks when its Click tree cannot be constructed."""
        if seen is None:
            seen = set()
        app_id = id(app)
        if app_id in seen:
            return
        seen.add(app_id)

        commands = getattr(app, "registered_commands", None)
        if not isinstance(commands, list):
            return

        for command in commands:
            callback = getattr(command, "callback", None)
            if not callable(callback):
                continue

            command_name = getattr(command, "name", None) or callback.__name__
            name = f"{prefix}{command_name}".replace("-", "_")
            description = (
                getattr(command, "help", None) or inspect.getdoc(callback) or ""
            )
            signature = inspect.signature(callback)
            try:
                annotations = inspect.get_annotations(callback, eval_str=True)
            except Exception:
                annotations = inspect.get_annotations(callback, eval_str=False)

            parameters: list[ParameterInfo] = []
            for param in signature.parameters.values():
                metadata = param.default
                raw_default = getattr(metadata, "default", metadata)
                if raw_default is inspect.Parameter.empty or raw_default is Ellipsis:
                    default: Any = _SENTINEL
                else:
                    default = raw_default

                help_text = getattr(metadata, "help", "")
                parameters.append(
                    ParameterInfo(
                        name=param.name,
                        type_annotation=python_type_name(
                            annotations.get(param.name, param.annotation)
                        ),
                        default=default,
                        description=help_text if isinstance(help_text, str) else "",
                    )
                )

            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    parameters=parameters,
                    return_type="str",
                    function_body=extract_function_body(callback),
                    is_async=inspect.iscoroutinefunction(callback),
                    source_imports=extract_source_imports(callback),
                )
            )

        groups = getattr(app, "registered_groups", None)
        if not isinstance(groups, list):
            return
        for group in groups:
            nested = getattr(group, "typer_instance", None)
            if nested is None:
                continue
            group_name = getattr(group, "name", None)
            nested_prefix = f"{prefix}{group_name}_" if group_name else prefix
            self._extract_registered_app(nested, tools, nested_prefix, seen)

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
        callback = getattr(cmd, "callback", None)
        callback_params: dict[str, inspect.Parameter] = {}
        if callback is not None:
            try:
                callback_params = dict(inspect.signature(callback).parameters)
            except (TypeError, ValueError):
                pass

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
            else:
                original = callback_params.get(param.name)
                original_help = getattr(
                    getattr(original, "default", None), "help", None
                )
                if isinstance(original_help, str):
                    desc = original_help

            params.append(
                ParameterInfo(
                    name=param.name,
                    type_annotation=type_str,
                    default=default,
                    description=desc,
                )
            )

        # Extract function body and async status from the callback
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
