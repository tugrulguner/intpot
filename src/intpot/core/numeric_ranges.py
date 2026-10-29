"""Bounded CLI numeric validation, without exporting custom range semantics."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from intpot.core.models import _SENTINEL, ToolInfo, ToolSchema


class UnsupportedCLINumericRangeError(Exception):
    """Generation cannot preserve the source range's validation/transformation."""


def cli_numeric_range(metadata: Any, *, constructed: bool) -> dict[str, Any]:
    """Read ordinary inclusive ranges structurally across vendored Click versions."""
    minimum = getattr(metadata, "min", None)
    maximum = getattr(metadata, "max", None)
    clamp = getattr(metadata, "clamp", False)
    range_class = type(metadata).__name__
    if constructed and range_class not in ("IntRange", "FloatRange"):
        # A custom range-like type must not silently become a plain primitive.
        if hasattr(metadata, "min") or hasattr(metadata, "max"):
            return {"unsupported_numeric_range": True}
        return {}
    if minimum is None and maximum is None and not clamp:
        return {}
    unsupported = bool(
        clamp
        or getattr(metadata, "min_open", False)
        or getattr(metadata, "max_open", False)
    )
    unsupported |= any(
        isinstance(bound, bool)
        or not isinstance(bound, (int, float))
        or (isinstance(bound, float) and not math.isfinite(bound))
        for bound in (minimum, maximum)
        if bound is not None
    )
    if unsupported:
        return {"unsupported_numeric_range": True}
    return {"minimum": minimum, "maximum": maximum}


def cli_range_default(
    details: dict[str, Any], type_name: str, default: Any
) -> tuple[dict[str, Any], Any]:
    if (
        not any(details.get(key) is not None for key in ("minimum", "maximum"))
        or default is _SENTINEL
        or default is None
    ):
        return details, default
    if (
        isinstance(default, bool)
        or not isinstance(default, (int, float))
        or (type_name == "int" and not isinstance(default, int))
    ):
        return {"unsupported_numeric_range": True}, default
    if isinstance(default, float) and not math.isfinite(default):
        return {"unsupported_numeric_range": True}, default
    minimum, maximum = details.get("minimum"), details.get("maximum")
    if (minimum is not None and default < minimum) or (
        maximum is not None and default > maximum
    ):
        return {"unsupported_numeric_range": True}, default
    return details, float(default) if type_name == "float" else default


def guard_cli_numeric_ranges(tools: Iterable[ToolInfo | ToolSchema]) -> None:
    affected = [
        f"{tool.interface_name or tool.name}.{parameter.binding_name or parameter.name}"
        for tool in tools
        for parameter in tool.parameters
        if parameter.unsupported_numeric_range
    ]
    if affected:
        raise UnsupportedCLINumericRangeError(
            f"Cannot preserve CLI numeric range semantics for {', '.join(affected)}: "
            "clamping, exclusive endpoints, custom ranges and unsupported defaults require explicit implementation."
        )
