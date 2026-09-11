"""Shared Jinja2 rendering logic for generators."""

from __future__ import annotations

import ast
import re
import symtable
import textwrap
from collections.abc import Sequence
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from intpot.core.generators.base import RenderableTool
from intpot.core.models import _default_imports, _source_default

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

_TYPING_NAMES = {
    "Any",
    "Dict",
    "FrozenSet",
    "List",
    "Optional",
    "Set",
    "Tuple",
    "Union",
    "Callable",
    "Iterator",
    "Generator",
    "Sequence",
    "Mapping",
    "Literal",
    "ClassVar",
    "Final",
    "Annotated",
}


def _extract_typing_imports(tools: Sequence[RenderableTool]) -> list[str]:
    """Scan all type annotations across tools and return required typing imports."""
    found: set[str] = set()
    for tool in tools:
        _scan_type_string(tool.return_type, found)
        for param in tool.parameters:
            _scan_type_string(param.type_annotation, found)
    return sorted(found)


def _scan_type_string(type_str: str, found: set[str]) -> None:
    """Extract typing module names from a type annotation string."""
    for name in _TYPING_NAMES:
        if re.search(rf"\b{name}\b", type_str):
            found.add(name)


def _to_pascal_case(name: str) -> str:
    """Convert a snake_case or camelCase name to PascalCase."""
    # Split on underscores and capitalize each part
    parts = re.split(r"[_\-]+", name)
    # Also split on camelCase boundaries
    expanded: list[str] = []
    for part in parts:
        expanded.extend(re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", part) or [part])
    return "".join(word.capitalize() for word in expanded if word)


def _escape_docstring(text: str) -> str:
    """Make text safe to drop between triple quotes.

    Backslashes are escaped first, or escaping the quotes would re-introduce
    them. Text ending in a double quote is escaped too, otherwise it runs into
    the closing delimiter and starts a fourth quote.

    This is only for docstrings. Where a string *literal* is needed, use the
    `repr` filter instead: hand-written quotes around arbitrary text produced
    'SyntaxError: unterminated string literal' for any description containing a
    quote or a newline.
    """
    text = text.replace("\\", "\\\\")
    text = text.replace('"""', '\\"\\"\\"')
    if text.endswith('"'):
        text = text[:-1] + '\\"'
    return text


def _private_aliases(tools: Sequence[RenderableTool]) -> dict[str, str]:
    """Choose deterministic helper aliases that cannot collide with source globals."""
    occupied = {tool.name for tool in tools}
    for tool in tools:
        occupied.update(parameter.name for parameter in tool.parameters)
        for source_import in tool.source_imports:
            occupied.update(re.findall(r"\b[A-Za-z_]\w*\b", source_import))

    def unique(base: str) -> str:
        candidate = base
        while candidate in occupied:
            candidate += "_"
        occupied.add(candidate)
        return candidate

    aliases = {
        module: unique(f"_intpot_defaults_{module}")
        for module in (
            "builtins",
            "collections",
            "datetime",
            "decimal",
            "fractions",
            "pathlib",
            "uuid",
        )
    }
    for framework, names in {
        "cli": ("asyncio", "typer"),
        "mcp": ("FastMCP",),
        "api": ("uvicorn",),
    }.items():
        for name in names:
            aliases[f"{framework}:{name}"] = unique(
                f"_intpot_{framework}_{name.lower()}"
            )
    for name in (
        "Body",
        "Cookie",
        "FastAPI",
        "File",
        "Form",
        "Header",
        "Path",
        "Query",
    ):
        aliases[f"fastapi:{name}"] = unique(f"_intpot_fastapi_{name}")
    return aliases


def _bound_name(alias: ast.alias, statement: ast.Import | ast.ImportFrom) -> str:
    return alias.asname or (
        alias.name
        if isinstance(statement, ast.ImportFrom)
        else alias.name.split(".", 1)[0]
    )


def _generated_binding_collisions(
    template_name: str,
    tools: Sequence[RenderableTool],
    extra_imports: Sequence[str],
    typing_imports: Sequence[str],
) -> set[str]:
    retained = set(typing_imports)
    for source_import in extra_imports:
        try:
            statement = ast.parse(source_import).body[0]
        except (SyntaxError, IndexError):
            continue
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            retained.update(_bound_name(alias, statement) for alias in statement.names)

    if template_name == "cli_app.py.j2":
        generated = {"app"}
        generated.update(tool.name for tool in tools)
        generated.update(f"_{tool.name}_impl" for tool in tools if tool.function_body)
    elif template_name == "mcp_server.py.j2":
        generated = {"mcp"}
        generated.update(tool.name for tool in tools)
    elif template_name == "api_app.py.j2":
        generated = {"app"}
        generated.update(tool.name for tool in tools)
    else:
        generated = set()
    return retained & generated


def _collect_extra_imports(
    tools: Sequence[RenderableTool], aliases: dict[str, str]
) -> list[str]:
    """Keep imported bindings still referenced by the generated implementation."""
    generated_typing_names = set(_extract_typing_imports(tools))
    seen: set[str] = set()
    source_imports: list[str] = []
    default_imports: set[str] = set()
    for tool in tools:
        referenced = _referenced_names((tool,))
        for imp in tool.source_imports:
            for retained in _retained_imports(imp, referenced, generated_typing_names):
                if retained not in seen:
                    seen.add(retained)
                    source_imports.append(retained)
        for parameter in tool.parameters:
            if parameter.required:
                continue
            for imp in sorted(_default_imports(parameter.default, aliases)):
                default_imports.add(imp)
    return sorted(source_imports) + sorted(default_imports)


def _referenced_names(tools: Sequence[RenderableTool]) -> set[str]:
    """Names that survive into generated bodies and annotations."""
    referenced: set[str] = set()
    for tool in tools:
        if tool.function_body:
            referenced.update(_body_global_names(tool))
        referenced.update(_loaded_names(tool.return_type, mode="eval"))
        for parameter in tool.parameters:
            referenced.update(_loaded_names(parameter.type_annotation, mode="eval"))
    return referenced


def _body_global_names(tool: RenderableTool) -> set[str]:
    """Return globals loaded by a body, excluding parameters and local bindings."""
    parameters = ", ".join(parameter.name for parameter in tool.parameters)
    body = textwrap.indent(tool.function_body or "pass", "    ")
    declaration = "async def" if tool.is_async else "def"
    source = f"{declaration} _intpot_generated_tool({parameters}):\n{body}\n"
    try:
        syntax_tree = ast.parse(source)
        module_table = symtable.symtable(source, "<intpot-tool>", "exec")
    except SyntaxError:
        loaded = _loaded_names(tool.function_body or "", mode="exec")
        return loaded - {parameter.name for parameter in tool.parameters}

    referenced: set[str] = set()

    def collect(table: symtable.SymbolTable) -> None:
        referenced.update(
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_global() and symbol.is_referenced()
        )
        for child in table.get_children():
            collect(child)

    for function_table in module_table.get_children():
        collect(function_table)
    referenced.update(_special_scope_reads(syntax_tree))
    referenced.update(_nested_annotation_names(syntax_tree))
    return referenced


class _SpecialScopeReadCollector(ast.NodeVisitor):
    """Collect reads that Python's symbol table does not classify as references."""

    def __init__(self) -> None:
        self.referenced: set[str] = set()
        self._scopes: list[tuple[str, set[str]]] = []
        self._class_bound: list[set[str]] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        global_collector = _GlobalDeclarationCollector()
        for statement in node.body:
            global_collector.visit(statement)
        self._scopes.append(("function", global_collector.names))
        for statement in node.body:
            self.visit(statement)
        self._scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        definition_expressions = [
            *node.decorator_list,
            *node.args.defaults,
            *node.args.kw_defaults,
        ]
        self._retain_class_definition_fallbacks(node.name, definition_expressions)
        for expression in definition_expressions:
            if expression is not None:
                self.visit(expression)
        self._visit_function(node)
        self._bind_class_name(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        definition_expressions = [
            *node.decorator_list,
            *node.args.defaults,
            *node.args.kw_defaults,
        ]
        self._retain_class_definition_fallbacks(node.name, definition_expressions)
        for expression in definition_expressions:
            if expression is not None:
                self.visit(expression)
        self._visit_function(node)
        self._bind_class_name(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        definition_expressions = [
            *node.decorator_list,
            *node.bases,
            *(keyword.value for keyword in node.keywords),
        ]
        self._retain_class_definition_fallbacks(node.name, definition_expressions)
        for expression in definition_expressions:
            self.visit(expression)
        global_collector = _GlobalDeclarationCollector()
        for statement in node.body:
            global_collector.visit(statement)
        self._scopes.append(("class", global_collector.names))
        self._class_bound.append(set())
        for statement in node.body:
            self.visit(statement)
        self._class_bound.pop()
        self._scopes.pop()
        self._bind_class_name(node.name)

    def visit_Name(self, node: ast.Name) -> None:
        if (
            self._in_class_scope()
            and isinstance(node.ctx, ast.Load)
            and node.id not in self._class_bound[-1]
        ):
            self.referenced.add(node.id)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        if self._in_class_scope():
            for default in [*node.args.defaults, *node.args.kw_defaults]:
                if default is not None:
                    self.visit(default)
            return
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)

    def _visit_comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        if self._in_class_scope() and node.generators:
            self.visit(node.generators[0].iter)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self._in_class_scope():
            self._class_bound[-1].update(
                alias.asname or alias.name.split(".", 1)[0] for alias in node.names
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._in_class_scope():
            self._class_bound[-1].update(
                alias.asname or alias.name for alias in node.names if alias.name != "*"
            )

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name) and self._reads_existing_binding(
            node.target.id
        ):
            self.referenced.add(node.target.id)
        self.generic_visit(node)
        if self._in_class_scope() and isinstance(node.target, ast.Name):
            self._class_bound[-1].add(node.target.id)

    def visit_Delete(self, node: ast.Delete) -> None:
        deleted: set[str] = set()
        for target in node.targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Del):
                    deleted.add(child.id)
                    if self._scopes and child.id in self._scopes[-1][1]:
                        self.referenced.add(child.id)
        self.generic_visit(node)
        if self._in_class_scope():
            self._class_bound[-1].difference_update(deleted)

    def visit_For(self, node: ast.For) -> None:
        self._visit_class_loop(node.target, node.iter, node.body, node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_class_loop(node.target, node.iter, node.body, node.orelse)

    def visit_With(self, node: ast.With) -> None:
        self._visit_class_with(node.items, node.body)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_class_with(node.items, node.body)

    def _visit_class_with(
        self, items: list[ast.withitem], body: list[ast.stmt]
    ) -> None:
        if not self._in_class_scope():
            for item in items:
                self.visit(item.context_expr)
                if item.optional_vars is not None:
                    self.visit(item.optional_vars)
            for statement in body:
                self.visit(statement)
            return
        for item in items:
            targets = (
                _stored_names(item.optional_vars)
                if item.optional_vars is not None
                else set()
            )
            self.referenced.update(
                (targets & _loaded_ast_names(item.context_expr)) - self._class_bound[-1]
            )
            self.visit(item.context_expr)
            self._class_bound[-1].update(targets)
        for statement in body:
            self.visit(statement)

    def visit_If(self, node: ast.If) -> None:
        if not self._in_class_scope():
            self.generic_visit(node)
            return
        self.visit(node.test)
        before = set(self._class_bound[-1])
        self._class_bound[-1] = set(before)
        for statement in node.body:
            self.visit(statement)
        body_bound = set(self._class_bound[-1])
        self._class_bound[-1] = set(before)
        for statement in node.orelse:
            self.visit(statement)
        else_bound = set(self._class_bound[-1])
        self._class_bound[-1] = body_bound & else_bound

    def visit_While(self, node: ast.While) -> None:
        if not self._in_class_scope():
            self.generic_visit(node)
            return
        self.visit(node.test)
        before = set(self._class_bound[-1])
        for statements in (node.body, node.orelse):
            self._class_bound[-1] = set(before)
            for statement in statements:
                self.visit(statement)
        self._class_bound[-1] = before

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_class_try(node.body, node.handlers, node.orelse, node.finalbody)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._visit_class_try(node.body, node.handlers, node.orelse, node.finalbody)

    def _visit_class_try(
        self,
        body: list[ast.stmt],
        handlers: list[ast.ExceptHandler],
        orelse: list[ast.stmt],
        finalbody: list[ast.stmt],
    ) -> None:
        if not self._in_class_scope():
            for statement in [*body, *handlers, *orelse, *finalbody]:
                self.visit(statement)
            return
        before = set(self._class_bound[-1])
        for statements in (body, orelse):
            self._class_bound[-1] = set(before)
            for statement in statements:
                self.visit(statement)
        for handler in handlers:
            self._class_bound[-1] = set(before)
            self.visit(handler)
        deleted_handler_names = {handler.name for handler in handlers if handler.name}
        self._class_bound[-1] = before - deleted_handler_names
        for statement in finalbody:
            self.visit(statement)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if not self._in_class_scope() or node.name is None:
            self.generic_visit(node)
            return
        name = node.name
        if (
            node.type is not None
            and name not in self._class_bound[-1]
            and name in _loaded_ast_names(node.type)
        ):
            self.referenced.add(name)
        if node.type is not None:
            self.visit(node.type)
        previous = set(self._class_bound[-1])
        self._class_bound[-1].add(name)
        for statement in node.body:
            self.visit(statement)
        self._class_bound[-1] = previous

    def _visit_class_loop(
        self,
        target: ast.expr,
        iterator: ast.expr,
        body: list[ast.stmt],
        orelse: list[ast.stmt],
    ) -> None:
        if not self._in_class_scope():
            self.generic_visit(iterator)
            self.generic_visit(target)
            for statement in [*body, *orelse]:
                self.visit(statement)
            return
        targets = _stored_names(target)
        loads = _loaded_ast_names(iterator)
        self.referenced.update((targets & loads) - self._class_bound[-1])
        self.visit(iterator)
        previous = set(self._class_bound[-1])
        self._class_bound[-1].update(targets)
        for statement in body:
            self.visit(statement)
        self._class_bound[-1] = set(previous)
        for statement in orelse:
            self.visit(statement)
        self._class_bound[-1] = previous

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if self._in_class_scope() and isinstance(node.target, ast.Name):
            name = node.target.id
            if name not in self._class_bound[-1] and name in _loaded_ast_names(
                node.value
            ):
                self.referenced.add(name)
            self.visit(node.value)
            self._class_bound[-1].add(name)
            return
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        if not self._in_class_scope():
            self.generic_visit(node)
            return
        captured = set().union(*(_pattern_names(case.pattern) for case in node.cases))
        self.referenced.update(
            (captured & _loaded_ast_names(node.subject)) - self._class_bound[-1]
        )
        self.visit(node.subject)
        before = set(self._class_bound[-1])
        for case in node.cases:
            self._class_bound[-1] = before | _pattern_names(case.pattern)
            if case.guard is not None:
                self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)
        self._class_bound[-1] = before

    def visit_Assign(self, node: ast.Assign) -> None:
        targets: set[str] = set()
        if self._in_class_scope():
            targets = {
                child.id
                for target in node.targets
                for child in ast.walk(target)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
            }
            loads = {
                child.id
                for child in ast.walk(node.value)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            }
            self.referenced.update((targets & loads) - self._class_bound[-1])
        self.generic_visit(node)
        if self._in_class_scope():
            self._class_bound[-1].update(targets)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            self._in_class_scope()
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and node.target.id not in self._class_bound[-1]
            and any(
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id == node.target.id
                for child in ast.walk(node.value)
            )
        ):
            self.referenced.add(node.target.id)
        self.generic_visit(node)
        if (
            self._in_class_scope()
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            self._class_bound[-1].add(node.target.id)

    def _reads_existing_binding(self, name: str) -> bool:
        if not self._scopes:
            return False
        kind, globals_ = self._scopes[-1]
        if kind == "class":
            return name not in self._class_bound[-1]
        return name in globals_

    def _in_class_scope(self) -> bool:
        return bool(self._scopes and self._scopes[-1][0] == "class")

    def _retain_class_definition_fallbacks(
        self, bound_name: str, expressions: Sequence[ast.expr | None]
    ) -> None:
        if not self._in_class_scope() or bound_name in self._class_bound[-1]:
            return
        if any(
            bound_name in _loaded_ast_names(expression)
            for expression in expressions
            if expression is not None
        ):
            self.referenced.add(bound_name)

    def _bind_class_name(self, name: str) -> None:
        if self._in_class_scope():
            self._class_bound[-1].add(name)


def _stored_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
    }


def _pattern_names(node: ast.pattern) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, (ast.MatchAs, ast.MatchStar)) and child.name is not None:
            names.add(child.name)
        elif isinstance(child, ast.MatchMapping) and child.rest is not None:
            names.add(child.rest)
    return names


def _loaded_ast_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


class _GlobalDeclarationCollector(ast.NodeVisitor):
    """Collect a function's global declarations without entering nested scopes."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_Global(self, node: ast.Global) -> None:
        self.names.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass


def _special_scope_reads(tree: ast.AST) -> set[str]:
    collector = _SpecialScopeReadCollector()
    collector.visit(tree)
    return collector.referenced


def _nested_annotation_names(tree: ast.AST) -> set[str]:
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            referenced.update(_annotation_ast_names(node.annotation))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                referenced.update(_annotation_ast_names(node.returns))
        elif isinstance(node, ast.AnnAssign):
            referenced.update(_annotation_ast_names(node.annotation))
    return referenced


def _loaded_names(source: str, *, mode: str) -> set[str]:
    try:
        tree = ast.parse(source, mode=mode)
    except SyntaxError:
        # Annotation strings can contain forward-reference syntax that is not
        # independently parseable. Keeping matching bindings is safer than
        # silently deleting one the generated module may need.
        return set(re.findall(r"\b[A-Za-z_]\w*\b", source))
    if mode == "eval":
        return _annotation_ast_names(tree)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _annotation_ast_names(node: ast.AST, *, parse_strings: bool = True) -> set[str]:
    """Collect annotation globals without treating Literal values as types."""
    if isinstance(node, ast.Name):
        return {node.id} if isinstance(node.ctx, ast.Load) else set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _loaded_names(node.value, mode="eval") if parse_strings else set()
    if isinstance(node, ast.Subscript):
        names = _annotation_ast_names(node.value, parse_strings=parse_strings)
        root = node.value
        subscript_name = (
            root.attr
            if isinstance(root, ast.Attribute)
            else (root.id if isinstance(root, ast.Name) else None)
        )
        elements = (
            list(node.slice.elts) if isinstance(node.slice, ast.Tuple) else [node.slice]
        )
        if subscript_name == "Literal":
            for element in elements:
                names.update(_annotation_ast_names(element, parse_strings=False))
        elif subscript_name == "Annotated" and elements:
            names.update(_annotation_ast_names(elements[0], parse_strings=True))
            for element in elements[1:]:
                names.update(_annotation_ast_names(element, parse_strings=False))
        else:
            for element in elements:
                names.update(
                    _annotation_ast_names(element, parse_strings=parse_strings)
                )
        return names
    names: set[str] = set()
    for child in ast.iter_child_nodes(node):
        names.update(_annotation_ast_names(child, parse_strings=parse_strings))
    return names


def _retained_imports(
    statement: str,
    referenced: set[str],
    generated_typing_names: set[str],
) -> list[str]:
    """Split an import and retain aliases by their actual bound names."""
    try:
        tree = ast.parse(statement)
    except SyntaxError:
        return [statement]
    if len(tree.body) != 1 or not isinstance(
        tree.body[0], (ast.Import, ast.ImportFrom)
    ):
        return [statement]

    node = tree.body[0]
    retained: list[str] = []
    for alias in node.names:
        if alias.name == "*":
            return [statement]
        bound_name = _bound_name(alias, node)
        if bound_name not in referenced:
            continue
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "typing"
            and alias.asname is None
            and alias.name in generated_typing_names
        ):
            continue
        if isinstance(node, ast.ImportFrom):
            single: ast.stmt = ast.ImportFrom(
                module=node.module,
                names=[alias],
                level=node.level,
            )
        else:
            single = ast.Import(names=[alias])
        retained.append(ast.unparse(single))
    return retained


# Only runs that precede a top-level line: those are the template seams. A run
# inside a function body or a docstring belongs to the source and is left alone.
_EXCESS_BLANK_LINES = re.compile(r"\n{4,}(?=\S)")


def _normalize_blank_lines(code: str) -> str:
    """Collapse runs of more than two blank lines before a top-level statement.

    Templates branch on whether a tool has a preserved body, and the two
    branches do not carry the same trailing whitespace. Normalising here keeps
    every generator's output at PEP 8's two-blank-line maximum without spreading
    whitespace-control tags through the templates.
    """
    return _EXCESS_BLANK_LINES.sub("\n\n\n", code)


def render_template(template_name: str, **kwargs: object) -> str:
    tools: Sequence[RenderableTool] | None = None
    aliases: dict[str, str] = {}
    candidate_tools = kwargs.get("tools")
    if isinstance(candidate_tools, Sequence) and not isinstance(
        candidate_tools, (str, bytes)
    ):
        tools = candidate_tools
        aliases = _private_aliases(tools)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    env.filters["repr"] = repr
    env.filters["source_default"] = lambda value: _source_default(value, aliases)
    env.filters["fastapi_alias"] = lambda name: aliases[f"fastapi:{name}"]
    env.filters["pascal"] = _to_pascal_case
    env.filters["escape_doc"] = _escape_docstring
    template = env.get_template(template_name)

    # Auto-extract typing imports and extra imports if tools are provided
    if tools is not None:
        if "typing_imports" not in kwargs:
            kwargs = dict(kwargs, typing_imports=_extract_typing_imports(tools))
        if "extra_imports" not in kwargs:
            kwargs = dict(kwargs, extra_imports=_collect_extra_imports(tools, aliases))
        collisions = _generated_binding_collisions(
            template_name,
            tools,
            kwargs["extra_imports"],  # type: ignore[arg-type]
            kwargs["typing_imports"],  # type: ignore[arg-type]
        )
        if collisions:
            names = ", ".join(sorted(collisions))
            raise ValueError(
                "Cannot generate standalone code because retained source import "
                f"bindings collide with generated names: {names}"
            )
        kwargs = dict(kwargs, generated_aliases=aliases)

    return _normalize_blank_lines(template.render(**kwargs))
