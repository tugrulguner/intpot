"""Bounded static binding checks for emitted module-level function definitions."""

from __future__ import annotations

import ast
import builtins

MODULE_BINDINGS = {
    "__name__",
    "__doc__",
    "__package__",
    "__loader__",
    "__spec__",
    "__file__",
    "__cached__",
    "__builtins__",
}


class _EagerLoads(ast.NodeVisitor):
    """Visit expression evaluation, excluding deferred code and local comp names."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.locals: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id not in self.locals:
            self.names.add(node.id)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Creating a lambda evaluates its defaults, not its body.
        for value in [*node.args.defaults, *node.args.kw_defaults]:
            if value is not None:
                self.visit(value)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        # Only the outer iterable is evaluated when the generator is created.
        self.visit(node.generators[0].iter)

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.DictComp) -> None:
        outer = self.locals.copy()
        for generator in node.generators:
            self.visit(generator.iter)
            self.locals.update(
                child.id
                for child in ast.walk(generator.target)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
            )
            for condition in generator.ifs:
                self.visit(condition)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.locals = outer

    visit_ListComp = _comprehension
    visit_SetComp = _comprehension
    visit_DictComp = _comprehension


def definition_time_missing(module: ast.Module) -> dict[str, list[str]]:
    """Find absent/late globals in emitted function defaults and eager annotations.

    This does not evaluate expressions, resolve string/lazy annotations, follow calls,
    validate imports, or prove that initializers succeed. It checks the ordered
    straight-line definitions emitted by the generators, not arbitrary module control flow.
    """
    postponed = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in module.body
    )
    available = set(dir(builtins)) | MODULE_BINDINGS
    missing: dict[str, list[str]] = {}
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            expressions = [*node.decorator_list, *node.args.defaults]
            expressions.extend(
                value for value in node.args.kw_defaults if value is not None
            )
            if not postponed:
                arguments = [
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                ]
                if node.args.vararg:
                    arguments.append(node.args.vararg)
                if node.args.kwarg:
                    arguments.append(node.args.kwarg)
                expressions.extend(
                    arg.annotation for arg in arguments if arg.annotation is not None
                )
                if node.returns is not None:
                    expressions.append(node.returns)
            loads = _EagerLoads()
            for expression in expressions:
                loads.visit(expression)
            unresolved = sorted(loads.names - available)
            if unresolved:
                missing[node.name] = unresolved
            available.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            available.update(
                alias.asname
                or (
                    alias.name.split(".", 1)[0]
                    if isinstance(node, ast.Import)
                    else alias.name
                )
                for alias in node.names
                if alias.name != "*"
            )
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.AnnAssign) and node.value is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            available.update(
                child.id
                for target in targets
                for child in ast.walk(target)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
            )
        elif isinstance(node, ast.ClassDef):
            available.add(node.name)
    return missing
