"""Bounded plain CLI string-list normalization, without source execution."""

from __future__ import annotations

import inspect
import types
from typing import Any, Union, get_args, get_origin

from intpot.core.models import _SENTINEL


def native_empty_list_default() -> Any:
    """Ask only the installed Typer builtin how zero occurrences normalize."""
    import typer.main

    factory: Any = getattr(typer.main, "generate_list_convertor", None)
    if callable(factory):
        converter: Any
        if "default_value" in inspect.signature(factory).parameters:
            converter = factory(None, default_value=None)
        else:
            converter = factory(None)
        value = converter(())
    else:
        normalize: Any = getattr(typer.main, "_normalize_collection_value", None)
        if not callable(normalize):
            raise TypeError("Unsupported native string-list normalization")
        value = normalize(
            types.SimpleNamespace(default=None, multiple=True, nargs=1), ()
        )
    if value is not None and (type(value) is not list or value):
        raise TypeError("Unsupported native string-list omission value")
    return value


def cli_string_list(
    annotation: Any,
    metadata: Any,
    default: Any,
    *,
    option: bool,
    automatic_envvar: bool = False,
    context_default: bool = False,
    unsupported_context: bool = False,
    native_parameter: Any = None,
) -> tuple[str, Any, int | None] | None:
    """Return proven primitive-list semantics or refuse unsupported collections.

    Enum collections are handled by their existing inspector before this helper.
    This helper reads metadata only; it never calls a source callback, parser,
    factory, environment lookup, normalization hook, or custom mapping getter.
    """
    origin = get_origin(annotation)
    nullable = False
    if origin in (Union, types.UnionType):
        values = tuple(item for item in get_args(annotation) if item is not type(None))
        if len(values) == 1 and len(get_args(annotation)) == 2:
            annotation = values[0]
            origin = get_origin(annotation)
            nullable = True
        elif any(get_origin(item) is list for item in values):
            raise TypeError("Only plain string-list collections are supported")
    if origin not in (list, tuple):
        return None
    if origin is not list or get_args(annotation) != (str,):
        raise TypeError("Only plain string-list collections are supported")
    if getattr(metadata, "default_factory", None) is not None:
        raise TypeError("String-list default factories are not supported")
    if getattr(metadata, "envvar", None) is not None or automatic_envvar:
        raise TypeError("Environment-backed string-list collections are not supported")
    if any(
        getattr(metadata, name, None) is not None for name in ("click_type", "parser")
    ):
        raise TypeError("Custom string-list parsers and types are not supported")
    prompt = getattr(metadata, "prompt", False)
    if prompt is not None and prompt is not False:
        raise TypeError("Prompt-backed string-list collections are not supported")
    if unsupported_context or context_default:
        raise TypeError("Context-backed string-list collections are not supported")
    if native_parameter is not None:
        native_type = getattr(native_parameter, "type", None)
        if native_type is not None and getattr(native_type, "name", None) not in {
            "text",
            "str",
            "string",
        }:
            raise TypeError("Custom native string-list element types are not supported")
        if option:
            if (
                not getattr(native_parameter, "multiple", False)
                or getattr(native_parameter, "nargs", 1) != 1
            ):
                raise TypeError("Unsupported native string-list option shape")
        elif getattr(native_parameter, "nargs", 1) != -1:
            raise TypeError("Unsupported native string-list argument shape")
    if option:
        if default is _SENTINEL:
            raise TypeError(
                "Only optional repeatable string-list options are supported"
            )
        if default is None:
            default = native_empty_list_default()
        if default is not None and (
            type(default) is not list or any(type(item) is not str for item in default)
        ):
            raise TypeError("Unsupported string-list option default")
        return ("Optional[list[str]]" if nullable else "list[str]", default, None)
    if default is not _SENTINEL or nullable:
        raise TypeError("Only required variadic string-list arguments are supported")
    return "list[str]", default, 1
