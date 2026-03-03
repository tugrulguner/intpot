"""Extract commands from a Typer app instance."""

from __future__ import annotations

from typing import Any

import click

from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def _click_type_to_str(param_type: Any) -> str:
    """Map Click parameter types to Python type name strings."""
    type_map = {
        click.STRING: "str",
        click.INT: "int",
        click.FLOAT: "float",
        click.BOOL: "bool",
    }
    for click_type, name in type_map.items():
        if param_type is click_type or isinstance(param_type, type(click_type)):
            return name
    return "str"


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

        commands: dict[str, click.Command] = {}
        if isinstance(click_group, click.Group):
            commands = click_group.commands
        elif isinstance(click_group, click.Command):
            commands = {click_group.name or "main": click_group}

        for cmd_name, cmd in commands.items():
            if cmd_name is None:
                continue

            description = cmd.help or ""

            params: list[ParameterInfo] = []
            for param in cmd.params:
                if param.name is None or param.name == "help":
                    continue

                type_str = _click_type_to_str(param.type)
                default = _SENTINEL
                if param.default is not None:
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

            tools.append(
                ToolInfo(
                    name=cmd_name,
                    description=description,
                    parameters=params,
                    return_type="str",
                )
            )

        return tools
