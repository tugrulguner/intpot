"""Conservative occurrence ranges in unchanged, captured original source."""

from __future__ import annotations

import ast
import hashlib
import tokenize
from pathlib import Path
from typing import Any


def body_reference_locations(
    emitted: ast.FunctionDef | ast.AsyncFunctionDef,
    location: tuple[str, int, int] | None,
    digest: str | None,
    retained_body: str | None = None,
) -> dict[str, list[dict[str, Any]]] | None:
    """Return verified body-name occurrences, or explicitly decline attribution."""
    if location is None or digest is None:
        return None
    path = Path(location[0])
    try:
        with tokenize.open(path) as stream:
            source = stream.read()
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != digest:
            return None
        candidates = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.lineno == location[1]
            and node.end_lineno == location[2]
        ]
        if len(candidates) != 1:
            return None
        original = candidates[0]

        def without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                return body[1:]
            return body

        original_body = ast.Module(
            body=without_docstring(original.body), type_ignores=[]
        )
        emitted_statements = without_docstring(emitted.body)
        retained = (
            without_docstring(ast.parse(retained_body).body)
            if retained_body is not None
            else emitted_statements
        )
        # The generated implementation may prefix its retained body with argument
        # guards. Require the entire retained body to match an emitted suffix and
        # the original, rather than treating generated offsets as original ones.
        if not retained or len(emitted_statements) < len(retained):
            return None
        retained_dump = ast.dump(ast.Module(body=retained, type_ignores=[]))
        if (
            ast.dump(original_body) != retained_dump
            or ast.dump(
                ast.Module(body=emitted_statements[-len(retained) :], type_ignores=[])
            )
            != retained_dump
        ):
            return None
        # Scope attribution beyond a plain function body is deliberately unknown.
        if any(
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.Lambda,
                    ast.ListComp,
                    ast.SetComp,
                    ast.DictComp,
                    ast.GeneratorExp,
                    ast.Global,
                    ast.Nonlocal,
                ),
            )
            or type(node).__name__ == "TypeAlias"
            for node in ast.walk(original_body)
        ):
            return None
        result: dict[str, list[dict[str, Any]]] = {}
        lines = source.splitlines()

        def column(line: int, offset: int) -> int:
            return len(lines[line - 1].encode("utf-8")[:offset].decode("utf-8")) + 1

        annotation_nodes = {
            id(child)
            for item in ast.walk(original_body)
            if isinstance(item, ast.AnnAssign)
            for child in ast.walk(item.annotation)
        }
        for node in ast.walk(original_body):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and id(node) not in annotation_nodes
            ):
                if node.end_lineno is None or node.end_col_offset is None:
                    return None
                result.setdefault(node.id, []).append(
                    {
                        "path": str(path),
                        "line": node.lineno,
                        "column": column(node.lineno, node.col_offset),
                        "end_line": node.end_lineno,
                        "end_column": column(node.end_lineno, node.end_col_offset),
                    }
                )
                if len(result[node.id]) > 64:
                    return None
        for occurrences in result.values():
            occurrences.sort(
                key=lambda span: (
                    span["line"],
                    span["column"],
                    span["end_line"],
                    span["end_column"],
                )
            )
        return result
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
        return None
