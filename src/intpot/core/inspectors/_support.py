"""Conservative same-module helper and immutable-literal recovery."""

from __future__ import annotations

import ast
import inspect
import types
from typing import Any

from intpot.core.inspectors._utils import _annotation_names


def extract_support_definitions(fn: Any) -> list[str]:
    """Recover a complete bounded closure from the inspected callable's module.

    Read source and existing globals only: never run module startup during recovery.
    Unsupported roots remain absent so normal missing-binding refusal is retained.
    """
    import builtins
    import symtable
    import sys

    fn = inspect.unwrap(fn)
    if not isinstance(fn, types.FunctionType) or fn.__closure__:
        return []
    try:
        origin = inspect.getsourcefile(fn)
        if not origin:
            return []
        with open(origin, encoding="utf-8") as source_file:
            tree = ast.parse(source_file.read())
        source_node = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == fn.__name__
            and min([node.lineno, *(item.lineno for item in node.decorator_list)])
            == fn.__code__.co_firstlineno
        )
    except (OSError, TypeError, SyntaxError, StopIteration):
        return []

    definitions: dict[str, ast.AST] = {}
    ambiguous: set[str] = set()
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [
                alias.asname
                or (
                    alias.name.split(".")[0]
                    if isinstance(node, ast.Import)
                    else alias.name
                )
                for alias in node.names
            ]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
        for name in names:
            if name in definitions:
                ambiguous.add(name)
            definitions[name] = node

    def globals_read(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        # Header evaluation is checked separately for recovered helpers.
        constructor = (
            ast.AsyncFunctionDef
            if isinstance(node, ast.AsyncFunctionDef)
            else ast.FunctionDef
        )
        clean = constructor(
            name=node.name,
            args=node.args,
            body=node.body,
            decorator_list=[],
            returns=None,
            type_comment=None,
        )
        table = symtable.symtable(
            ast.unparse(ast.fix_missing_locations(clean)), origin, "exec"
        )
        names: set[str] = set()

        def collect(scope: symtable.SymbolTable) -> None:
            names.update(
                symbol.get_name()
                for symbol in scope.get_symbols()
                if symbol.is_global() and symbol.is_referenced()
            )
            for child in scope.get_children():
                collect(child)

        for child in table.get_children():
            collect(child)
        return names

    def immutable(value: Any) -> bool:
        return type(value) in (type(None), bool, int, float, complex, str, bytes) or (
            type(value) is tuple and all(immutable(item) for item in value)
        )

    def value_matches(actual: Any, expected: Any) -> bool:
        """Keep type and representation identity, not Python's coercive equality."""
        if type(actual) is not type(expected):
            return False
        if type(expected) is tuple:
            return len(actual) == len(expected) and all(
                value_matches(a, b) for a, b in zip(actual, expected, strict=True)
            )
        if isinstance(expected, types.CodeType):
            return (
                actual.co_code == expected.co_code
                and actual.co_names == expected.co_names
                and actual.co_varnames == expected.co_varnames
                and actual.co_freevars == expected.co_freevars
                and actual.co_cellvars == expected.co_cellvars
                and actual.co_exceptiontable == expected.co_exceptiontable
                and value_matches(actual.co_consts, expected.co_consts)
            )
        return repr(actual) == repr(expected)

    def literal(node: ast.AST) -> Any:
        value = ast.literal_eval(node)
        if not immutable(value):
            raise ValueError("Mutable or dynamic support default")
        return value

    selected: dict[str, ast.AST] = {}
    visiting: set[str] = set()
    namespace = fn.__globals__

    def recover(name: str) -> bool:
        if name == fn.__name__:
            # Recursion of the registered tool is handled by the generator.
            return True
        if name in selected or name in visiting:
            return True
        if name not in namespace and name in vars(builtins):
            return True
        if name in ambiguous:
            return False
        node = definitions.get(name)
        value = namespace.get(name)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and (
                node.level or node.module == "__future__"
            ):
                return False
            alias = next(
                (
                    item
                    for item in node.names
                    if (
                        item.asname
                        or (
                            item.name.split(".")[0]
                            if isinstance(node, ast.Import)
                            else item.name
                        )
                    )
                    == name
                ),
                None,
            )
            if alias is None or alias.name == "*":
                return False
            module_name = (
                alias.name.split(".")[0]
                if isinstance(node, ast.Import) and not alias.asname
                else (alias.name if isinstance(node, ast.Import) else node.module)
            )
            module = sys.modules.get(module_name or "")
            expected = (
                module
                if isinstance(node, ast.Import)
                else (vars(module).get(alias.name) if module else None)
            )
            if value is not expected or expected is None:
                return False
            selected[name] = (
                ast.Import(names=[alias])
                if isinstance(node, ast.Import)
                else ast.ImportFrom(module=node.module, names=[alias], level=0)
            )
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            if isinstance(node, ast.Assign) and (
                len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name)
            ):
                return False
            if node.value is None:
                return False
            try:
                expected = literal(node.value)
            except (ValueError, TypeError, SyntaxError):
                return False
            if not value_matches(value, expected):
                return False
            # Drop variable annotations; the exported constant needs only its value.
            selected[name] = ast.Assign(
                targets=[ast.Name(id=name, ctx=ast.Store())], value=node.value
            )
            return True
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        if (
            node.decorator_list
            or not isinstance(value, types.FunctionType)
            or value.__closure__
            or value.__globals__ is not namespace
            or inspect.getsourcefile(value) != origin
            or value.__code__.co_firstlineno != node.lineno
            or any(
                isinstance(item, (ast.Global, ast.Nonlocal, ast.ClassDef))
                for item in ast.walk(node)
            )
        ):
            return False
        try:
            import __future__

            compiled = compile(
                ast.Module(body=[node], type_ignores=[]),
                origin,
                "exec",
                flags=value.__code__.co_flags & __future__.annotations.compiler_flag,
                dont_inherit=True,
            )
            candidate = next(
                item
                for item in compiled.co_consts
                if isinstance(item, types.CodeType) and item.co_name == node.name
            )
            if not value_matches(candidate, value.__code__):
                return False
            expected_defaults = tuple(
                literal(default) for default in node.args.defaults
            )
            expected_keywords = {
                arg.arg: literal(default)
                for arg, default in zip(
                    node.args.kwonlyargs, node.args.kw_defaults, strict=True
                )
                if default is not None
            }
            actual_keywords = value.__kwdefaults__ or {}
            if (
                not value_matches(value.__defaults__ or (), expected_defaults)
                or actual_keywords.keys() != expected_keywords.keys()
            ):
                return False
            if not all(
                value_matches(actual_keywords[name], expected)
                for name, expected in expected_keywords.items()
            ):
                return False
            if not immutable(value.__defaults__ or ()) or not all(
                immutable(item) for item in (value.__kwdefaults__ or {}).values()
            ):
                return False
            if any(
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id in {"globals", "locals", "eval", "exec", "__import__"}
                for item in ast.walk(node)
            ):
                return False
            headers = [
                arg.annotation
                for arg in (
                    *node.args.posonlyargs,
                    *node.args.args,
                    *node.args.kwonlyargs,
                )
                if arg.annotation is not None
            ]
            if node.returns is not None:
                headers.append(node.returns)
            if any(
                isinstance(item, ast.Call)
                for header in headers
                for item in ast.walk(header)
            ):
                return False
            dependencies = globals_read(node)
            for header in headers:
                dependencies.update(_annotation_names(header))
            # Helpers may recurse, but cannot call back through a transformed tool wrapper.
            if fn.__name__ in dependencies:
                return False
            visiting.add(name)
            if not all(
                recover(dependency) for dependency in sorted(dependencies - {name})
            ):
                return False
        except (ValueError, TypeError, SyntaxError):
            return False
        finally:
            visiting.discard(name)
        selected[name] = node
        return True

    try:
        roots = globals_read(source_node) - {fn.__name__}
    except (SyntaxError, ValueError):
        return []
    for name in sorted(roots):
        if isinstance(definitions.get(name), (ast.Import, ast.ImportFrom)):
            continue  # Existing source-import extraction owns direct tool imports.
        before = dict(selected)
        if not recover(name):
            selected = before
    imports = [
        ast.unparse(node)
        for node in selected.values()
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    support = [
        (definitions[name].lineno, ast.unparse(ast.fix_missing_locations(node)))
        for name, node in selected.items()
        if not isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    return list(dict.fromkeys(imports)) + [source for _, source in sorted(support)]
