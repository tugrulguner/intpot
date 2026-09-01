"""Shared Jinja2 rendering logic for generators."""

from __future__ import annotations

import re
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


_FRAMEWORK_IMPORT_MARKERS = {
    "typer",
    "fastmcp",
    "FastMCP",
    "fastapi",
    "FastAPI",
    "Body",
    "from typing import",
}


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
            "collections",
            "datetime",
            "decimal",
            "fractions",
            "pathlib",
            "uuid",
        )
    }
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


def _collect_extra_imports(
    tools: Sequence[RenderableTool], aliases: dict[str, str]
) -> list[str]:
    """Gather source_imports from all tools, dedupe, and filter framework imports."""
    seen: set[str] = set()
    result: list[str] = []
    for tool in tools:
        for imp in tool.source_imports:
            if imp in seen:
                continue
            seen.add(imp)
            if any(marker in imp for marker in _FRAMEWORK_IMPORT_MARKERS):
                continue
            result.append(imp)
        for parameter in tool.parameters:
            if parameter.required:
                continue
            for imp in sorted(_default_imports(parameter.default, aliases)):
                if imp not in seen:
                    seen.add(imp)
                    result.append(imp)
    return sorted(result)


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

    return _normalize_blank_lines(template.render(**kwargs))
