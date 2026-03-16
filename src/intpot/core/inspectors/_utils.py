"""Shared utilities for inspectors."""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any


def python_type_name(annotation: Any) -> str:
    """Convert a type annotation to a string representation."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return "str"
    if isinstance(annotation, type):
        return annotation.__name__
    # For typing generics (e.g. list[str], Optional[int]), use str()
    # but clean up the 'typing.' prefix for readability
    text = str(annotation)
    text = text.replace("typing.", "")
    return text


def extract_source_imports(fn: Any) -> list[str]:
    """Extract imports from the source file that are referenced in the function body.

    Returns a list of import statement strings, or [] on any failure.
    """
    # Unwrap decorated functions (e.g. Typer wraps callbacks)
    fn = inspect.unwrap(fn)

    try:
        source_file = inspect.getfile(fn)
    except (OSError, TypeError):
        return []

    try:
        with open(source_file) as f:
            module_source = f.read()
        module_tree = ast.parse(module_source)
    except (OSError, SyntaxError):
        return []

    # Collect all top-level import nodes and the names they bind
    import_nodes: list[tuple[ast.stmt, set[str]]] = []
    for node in module_tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {alias.asname or alias.name for alias in node.names}
            import_nodes.append((node, names))

    if not import_nodes:
        return []

    # Parse the function body to collect all Name references
    try:
        fn_source = textwrap.dedent(inspect.getsource(fn))
        fn_tree = ast.parse(fn_source)
    except (OSError, TypeError, SyntaxError):
        return []

    body_names: set[str] = set()
    for node in ast.walk(fn_tree):
        if isinstance(node, ast.Name):
            body_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # Capture top-level module name for `module.func()` patterns
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                body_names.add(root.id)

    # Keep only imports whose bound name appears in body
    result: list[str] = []
    seen: set[str] = set()
    for node, bound_names in import_nodes:
        if bound_names & body_names:
            line = ast.unparse(node)
            if line not in seen:
                seen.add(line)
                result.append(line)

    return result


def extract_function_body(fn: Any) -> str | None:
    """Extract the body of a function, skipping the def line and docstring.

    Returns the dedented body lines as a single string, or None if
    the source cannot be retrieved (e.g. dynamically generated functions).
    """
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return None

    try:
        source = textwrap.dedent(source)
        tree = ast.parse(source)
    except SyntaxError:
        return None

    if not tree.body or not isinstance(
        tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        return None

    func_node = tree.body[0]
    lines = source.splitlines()

    # Find where the body starts (skip decorator lines and def line)
    body_start_line = func_node.body[0].lineno  # 1-indexed

    # If the first body statement is a docstring, skip it
    first_stmt = func_node.body[0]
    if isinstance(first_stmt, ast.Expr) and isinstance(
        first_stmt.value, (ast.Constant, ast.Str)
    ):
        if len(func_node.body) <= 1:
            return None  # Only a docstring, no real body
        body_start_line = func_node.body[1].lineno

    body_lines = lines[body_start_line - 1 :]
    if not body_lines:
        return None

    body_text = textwrap.dedent("\n".join(body_lines))
    body_text = body_text.strip()
    return body_text if body_text else None
