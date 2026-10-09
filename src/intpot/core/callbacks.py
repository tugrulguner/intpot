"""Refuse generation that would discard source CLI parameter callbacks."""

from __future__ import annotations

from collections.abc import Iterable

from intpot.core.models import SourceType, ToolInfo, ToolSchema


class UnsupportedCLIParameterCallbackError(Exception):
    """Raised when generation would drop CLI validation or transformation."""


def guard_cli_parameter_callbacks(
    tools: Iterable[ToolInfo | ToolSchema], target: SourceType
) -> None:
    """Keep callback metadata inspectable without exporting its behavior."""
    if target not in (SourceType.API, SourceType.MCP):
        return
    affected = [
        f"{tool.interface_name or tool.name}.{parameter.binding_name or parameter.name}"
        for tool in tools
        for parameter in tool.parameters
        if parameter.unsupported_callback
    ]
    if affected:
        raise UnsupportedCLIParameterCallbackError(
            f"Cannot convert CLI parameter callbacks for {', '.join(affected)} "
            f"to {target.value} safely: callback validation or transformation "
            "cannot be preserved. Inspect the source and implement equivalent "
            "behavior explicitly before converting."
        )
