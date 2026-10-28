"""Bounded static binding paths through one tool's emitted definitions."""

from __future__ import annotations

import ast
import symtable
from collections import deque
from dataclasses import replace

from intpot.core.generators._render import _body_global_names
from intpot.core.models import ParameterSchema, ToolSchema


def definition_dependency_paths(
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    owned: set[str],
    root: str,
    tool: ToolSchema,
) -> dict[str, list[str]]:
    """Return one deterministic shortest body-reference path per owned definition.

    Paths are syntactic binding dependencies, not calls, execution traces or a
    claim that a branch executes. Missing owners remain absent rather than being
    attached to the tool by guesswork. Traverse only already emitted owned nodes.
    """
    edges: dict[str, set[str]] = {}
    rebound: set[str] = set()

    def collect_rebindings(table: symtable.SymbolTable) -> None:
        rebound.update(
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_global() and (symbol.is_assigned() or symbol.is_imported())
        )
        for child in table.get_children():
            collect_rebindings(child)

    for name in sorted(owned & functions.keys()):
        node = functions[name]
        try:
            table = symtable.symtable(
                ast.unparse(node), "<intpot-binding-path>", "exec"
            )
        except SyntaxError:
            # Existing diagnostics can inspect syntactically parsed bodies that
            # cannot form an independent symbol table. Do not change that policy.
            rebound.add(name)
            continue
        for child in table.get_children():
            collect_rebindings(child)
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        view = replace(
            tool,
            parameters=tuple(ParameterSchema(arg.arg) for arg in arguments),
            function_body="\n".join(ast.unparse(item) for item in node.body),
            is_async=isinstance(node, ast.AsyncFunctionDef),
        )
        edges[name] = _body_global_names(view) & owned
    if root not in edges or root in rebound:
        return {}
    edges = {owner: dependencies - rebound for owner, dependencies in edges.items()}
    paths = {root: [root]}
    pending = deque([root])
    while pending:
        owner = pending.popleft()
        for dependency in sorted(edges.get(owner, set())):
            if dependency not in paths:
                paths[dependency] = [*paths[owner], dependency]
                pending.append(dependency)
    return paths
