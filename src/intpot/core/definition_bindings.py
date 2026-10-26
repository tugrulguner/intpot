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


def annotation_missing(module: ast.Module) -> dict[str, list[str]]:
    """Find absent annotation globals in the completed emitted module, without eval."""
    available = set(dir(builtins)) | MODULE_BINDINGS
    typing_names: dict[str, str] = {}
    typing_modules: set[str] = set()
    collections_abc_names: set[str] = set()
    collections_abc_modules: dict[str, str] = {}
    builtin_generics = {"list", "dict", "tuple", "set", "frozenset", "type"}
    for statement in module.body:
        bound: set[str] = set()
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            bound.update(
                alias.asname
                or (
                    alias.name.split(".", 1)[0]
                    if isinstance(statement, ast.Import)
                    else alias.name
                )
                for alias in statement.names
                if alias.name != "*"
            )
        elif isinstance(
            statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            bound.add(statement.name)
        elif isinstance(statement, (ast.Assign, ast.AnnAssign)) and (
            isinstance(statement, ast.Assign) or statement.value is not None
        ):
            targets = (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
            bound.update(
                child.id
                for target in targets
                for child in ast.walk(target)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
            )
        available.update(bound)
        for name in bound:
            typing_names.pop(name, None)
        typing_modules.difference_update(bound)
        collections_abc_names.difference_update(bound)
        for name in bound:
            collections_abc_modules.pop(name, None)
        builtin_generics.difference_update(bound)
        if isinstance(statement, ast.ImportFrom) and statement.module in (
            "typing",
            "typing_extensions",
        ):
            for alias in statement.names:
                if alias.name != "*":
                    typing_names[alias.asname or alias.name] = alias.name
        elif isinstance(statement, ast.Import):
            typing_modules.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name in ("typing", "typing_extensions")
            )
            for alias in statement.names:
                if alias.name == "collections.abc":
                    collections_abc_modules[alias.asname or "collections"] = (
                        "abc" if alias.asname else "collections"
                    )
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.module == "collections.abc"
        ):
            collections_abc_names.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name == "Callable"
            )

    def collect(
        expression: ast.AST, *, direct: bool, strings: bool = True, depth: int = 0
    ) -> set[str]:
        if depth > 32:
            return set()
        if not strings:
            loads = _EagerLoads()
            if direct:
                loads.visit(expression)
            return loads.names
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            try:
                parsed = ast.parse(expression.value, mode="eval")
            except (SyntaxError, ValueError, RecursionError):
                # Invalid/unsupported type syntax is not evidence of a missing global.
                return set()
            return collect(parsed.body, direct=True, depth=depth + 1)
        if isinstance(expression, ast.Subscript):
            root = expression.value
            special = None
            if isinstance(root, ast.Name):
                special = typing_names.get(root.id)
                if special is None and root.id in collections_abc_names:
                    special = "Callable"
                if special is None and root.id in builtin_generics:
                    special = "generic"
            elif isinstance(root, ast.Attribute):
                if isinstance(root.value, ast.Name) and root.value.id in typing_modules:
                    special = root.attr
                elif (
                    isinstance(root.value, ast.Name)
                    and collections_abc_modules.get(root.value.id) == "abc"
                ):
                    special = root.attr if root.attr == "Callable" else None
                elif root.attr == "Callable" and isinstance(root.value, ast.Attribute):
                    module = root.value
                    if (
                        module.attr == "abc"
                        and isinstance(module.value, ast.Name)
                        and collections_abc_modules.get(module.value.id)
                        == "collections"
                    ):
                        special = "Callable"
            if special is None:
                # An assignment/custom subscription can interpret strings as data.
                # Check real expression loads, but do not guess its type grammar.
                return collect(expression, direct=direct, strings=False)
            elements = (
                list(expression.slice.elts)
                if isinstance(expression.slice, ast.Tuple)
                else [expression.slice]
            )
            names = collect(root, direct=direct, strings=False)
            for index, element in enumerate(elements):
                type_position = special != "Literal" and (
                    special != "Annotated" or index == 0
                )
                names.update(
                    collect(
                        element, direct=direct, strings=type_position, depth=depth + 1
                    )
                )
            return names
        if isinstance(expression, (ast.Tuple, ast.List)):
            return set().union(
                *(
                    collect(child, direct=direct, depth=depth + 1)
                    for child in expression.elts
                )
            )
        if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.BitOr):
            return collect(expression.left, direct=direct, depth=depth + 1) | collect(
                expression.right, direct=direct, depth=depth + 1
            )
        # Calls, metadata, lambdas and comprehensions contain value expressions,
        # not recursively parsed forward-reference strings. Never execute them.
        return collect(expression, direct=direct, strings=False)

    postponed = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in module.body
    )
    missing: dict[str, list[str]] = {}
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        expressions = [
            arg.annotation for arg in arguments if arg.annotation is not None
        ]
        if node.returns is not None:
            expressions.append(node.returns)
        names: set[str] = set()
        for expression in expressions:
            names.update(collect(expression, direct=postponed))
        unresolved = sorted(names - available)
        if unresolved:
            missing[node.name] = unresolved
    return missing
