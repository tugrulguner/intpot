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

    deleted_names = {
        node.id
        for node in ast.walk(syntax_tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Del)
    }
    referenced: set[str] = set()

    def collect(table: symtable.SymbolTable) -> None:
        referenced.update(
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_global()
            and (symbol.is_referenced() or symbol.get_name() in deleted_names)
        )
        for child in table.get_children():
            collect(child)

    for function_table in module_table.get_children():
        collect(function_table)
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
