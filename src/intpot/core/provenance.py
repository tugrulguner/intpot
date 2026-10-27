"""Bounded definition coordinates verified against an existing callable's code.

Reading and compiling trusted source does not execute module startup. Locations
identify definitions, not individual uses of a missing name or runtime fidelity.
"""

from __future__ import annotations

import ast
import sys
import tokenize
import types
from pathlib import Path
from typing import Any


def callable_source_location(fn: Any) -> tuple[str, int, int] | None:
    """Return original definition bounds only for a matching file-backed function."""
    if (
        not isinstance(fn, types.FunctionType)
        or fn.__closure__
        or hasattr(fn, "__wrapped__")
        or fn.__code__.co_filename.startswith("<")
    ):
        return None
    try:
        path = Path(fn.__code__.co_filename).resolve(strict=True)
        with tokenize.open(path) as stream:
            source = stream.read()
        tree = ast.parse(source, filename=str(path))
        compiled = compile(
            source,
            fn.__code__.co_filename,
            "exec",
            dont_inherit=True,
            optimize=sys.flags.optimize,
        )
        candidates: list[types.CodeType] = []

        def collect(code: types.CodeType) -> None:
            for item in code.co_consts:
                if isinstance(item, types.CodeType):
                    if item == fn.__code__:
                        candidates.append(item)
                    collect(item)

        collect(compiled)
        if len(candidates) != 1:
            return None
        nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == fn.__name__
            and min([node.lineno, *(d.lineno for d in node.decorator_list)])
            == fn.__code__.co_firstlineno
        ]
        if len(nodes) != 1 or nodes[0].end_lineno is None:
            return None
        node = nodes[0]
        assert node.end_lineno is not None
        return str(path), node.lineno, node.end_lineno
    except (OSError, ValueError, TypeError, SyntaxError, UnicodeError):
        return None


def inspected_callable_metadata(fn: Any) -> dict[str, Any]:
    """Capture existing recovered helpers and only their verified original bounds."""
    import inspect

    from intpot.core.inspectors._utils import extract_support_definitions

    definitions = extract_support_definitions(fn)
    # Existing recovery unwraps framework/user decorators. Attribute only the
    # recovered original definition, never the wrapper's runtime semantics.
    fn = inspect.unwrap(fn)
    location = callable_source_location(fn)
    helpers: dict[str, tuple[str, int, int]] = {}
    if location is not None:
        for definition in definitions:
            node = ast.parse(definition).body[0]
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            helper = fn.__globals__.get(node.name)
            helper_location = callable_source_location(helper)
            if helper_location is None or helper_location[0] != location[0]:
                continue
            try:
                with tokenize.open(helper_location[0]) as stream:
                    original_tree = ast.parse(stream.read())
            except (OSError, ValueError, SyntaxError, UnicodeError):
                continue
            originals = [
                item
                for item in original_tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == node.name
                and item.lineno == helper_location[1]
            ]
            if len(originals) == 1 and ast.unparse(originals[0]) == ast.unparse(node):
                helpers[node.name] = helper_location
    return {
        "support_definitions": definitions,
        "source_location": location,
        "support_source_locations": helpers,
    }


def location_dict(location: tuple[str, int, int] | None) -> dict[str, Any] | None:
    """Serialize a captured definition location without manufacturing coordinates."""
    if location is None:
        return None
    return {"path": location[0], "line": location[1], "end_line": location[2]}
