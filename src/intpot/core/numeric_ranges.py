"""Bounded CLI numeric validation, without exporting custom range semantics."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from intpot.core.models import _SENTINEL, ToolInfo, ToolSchema, _validate_numeric_bounds


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


def api_numeric_range(field_info: Any, type_name: str, default: Any) -> dict[str, Any]:
    """Recover ordinary finite inclusive bounds on primitive API parameters."""
    if type_name not in ("int", "float") or field_info is None:
        return {}
    refused = {"unsupported_api_numeric_range": True}
    if any(
        getattr(field_info, key, None) is not None
        for key in ("gt", "lt", "multiple_of", "allow_inf_nan")
    ) or getattr(field_info, "strict", False):
        return refused
    bounds = {}
    for attribute, key in (("ge", "minimum"), ("le", "maximum")):
        value = getattr(field_info, attribute, None)
        if value is not None:
            bounds[key] = value
    for metadata in getattr(field_info, "metadata", ()):
        if type(metadata).__module__ == "annotated_types":
            if type(metadata).__name__ == "Ge":
                bounds["minimum"] = metadata.ge
            elif type(metadata).__name__ == "Le":
                bounds["maximum"] = metadata.le
            else:
                return refused
        elif not isinstance(metadata, (str, int, float, bool, type(None))):
            return refused
    try:
        _validate_numeric_bounds(
            type_name, bounds.get("minimum"), bounds.get("maximum"), default
        )
    except ValueError:
        return refused
    return bounds


class UnsupportedAPINumericRangeError(Exception):
    """API numeric validation cannot be retained in generated interfaces."""


def guard_api_numeric_ranges(tools: Iterable[ToolInfo | ToolSchema]) -> None:
    affected = [
        f"{tool.interface_name or tool.name}.{parameter.binding_name or parameter.name}"
        for tool in tools
        for parameter in tool.parameters
        if parameter.unsupported_api_numeric_range
    ]
    if affected:
        raise UnsupportedAPINumericRangeError(
            f"Cannot preserve API numeric validation for {', '.join(affected)}: "
            "only ordinary finite inclusive bounds with supported defaults are retained; "
            "exclusive bounds, additional validators/constraints and unsupported defaults require explicit implementation."
        )


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
