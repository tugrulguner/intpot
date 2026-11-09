from __future__ import annotations

import ast
import hashlib
import tokenize
import types
from pathlib import Path
from typing import Any

from intpot.core.informational_callbacks import InformationalCallbackSpec
from intpot.core.provenance import callable_source_metadata


def _typer_exit() -> Any:
    import sys

    import typer

    candidate = vars(typer).get("Exit")
    if type(candidate) is not type:
        raise TypeError("Typer exit binding changed")
    module_name = vars(candidate).get("__module__")
    if type(module_name) is not str or module_name not in (
        "typer.exceptions",
        "typer._click.exceptions",
        "click.exceptions",
    ):
        raise TypeError("Unsupported Typer exit class")
    owner = sys.modules.get(module_name)
    if (
        candidate.__name__ != "Exit"
        or type(owner) is not types.ModuleType
        or vars(owner).get("Exit") is not candidate
    ):
        raise TypeError("Typer exit identity is unverified")
    return candidate


def _is_exit(expr: ast.expr, callback: types.FunctionType) -> bool:
    namespace = callback.__globals__
    if type(namespace) is not dict:
        return False
    if isinstance(expr, ast.Call):
        values = expr.args
        if expr.keywords:
            if expr.args or len(expr.keywords) != 1 or expr.keywords[0].arg != "code":
                return False
            values = [expr.keywords[0].value]
        if values and not (
            len(values) == 1
            and isinstance(values[0], ast.Constant)
            and type(values[0].value) is int
            and values[0].value == 0
        ):
            return False
        expr = expr.func
    local_names = callback.__code__.co_varnames + callback.__code__.co_cellvars
    if isinstance(expr, ast.Name):
        return expr.id not in local_names and namespace.get(expr.id) is _typer_exit()
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        if expr.value.id in local_names:
            return False
        module = namespace.get(expr.value.id)
        return (
            type(module) is types.ModuleType
            and vars(module).get(expr.attr) is _typer_exit()
        )
    return False


def qualify_informational_callback(spec: InformationalCallbackSpec) -> str:
    """Return verified source digest for the single supported informational shape."""
    if type(spec) is not InformationalCallbackSpec:
        raise TypeError("Expected InformationalCallbackSpec")
    try:
        callback = spec.resolve()
        import sys

        owner = sys.modules.get(spec.module)
        if type(owner) is not types.ModuleType or callback.__globals__ is not vars(
            owner
        ):
            raise TypeError("Callback globals do not match its module")
        metadata = callable_source_metadata(callback)
        location, digest = metadata["source_location"], metadata["source_digest"]
        if location is None or type(digest) is not str:
            raise TypeError("Callback source is unverified")
        with tokenize.open(Path(location[0])) as stream:
            source = stream.read()
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != digest:
            raise TypeError("Callback source changed")
        tree = ast.parse(source)
        funcs = [
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == spec.export
        ]
        if len(funcs) != 1:
            raise TypeError("Not a unique top-level function")
        node = funcs[0]
        params = [*node.args.posonlyargs, *node.args.args]
        if len(params) != 1:
            raise TypeError("Expected one parameter")
        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and type(body[0].value.value) is str
        ):
            body.pop(0)
        if len(body) != 1 or not isinstance(body[0], ast.If):
            raise TypeError("Unsupported callback body")
        branch = body[0]
        if (
            not isinstance(branch.test, ast.Name)
            or branch.test.id != params[0].arg
            or branch.orelse
        ):
            raise TypeError("Unsupported callback condition")
        if any(
            isinstance(
                n,
                (
                    ast.Return,
                    ast.Yield,
                    ast.YieldFrom,
                    ast.Await,
                    ast.Global,
                    ast.Nonlocal,
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            )
            for n in ast.walk(branch)
        ):
            raise TypeError("Unsupported control flow")
        if any(
            isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del))
            for n in ast.walk(branch)
        ):
            raise TypeError("Callback attribute mutation is unqualified")
        if (
            not branch.body
            or not isinstance(branch.body[-1], ast.Raise)
            or branch.body[-1].exc is None
            or not _is_exit(branch.body[-1].exc, callback)
        ):
            raise TypeError("Active branch must end in typer.Exit")
        return digest
    except TypeError:
        raise
    except Exception as exc:
        raise TypeError("Callback source could not be qualified") from exc
