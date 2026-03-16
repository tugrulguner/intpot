"""Shared Jinja2 rendering logic for generators."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from intpot.core.models import ToolInfo

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


def _extract_typing_imports(tools: list[ToolInfo]) -> list[str]:
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
    """Escape triple quotes in docstrings to prevent syntax errors."""
    return text.replace('"""', '\\"\\"\\"')


_FRAMEWORK_IMPORT_MARKERS = {
    "typer",
    "fastmcp",
    "FastMCP",
    "fastapi",
    "FastAPI",
    "Body",
    "from typing import",
}


def _collect_extra_imports(tools: list[ToolInfo]) -> list[str]:
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
    return sorted(result)


def render_template(template_name: str, **kwargs: object) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    env.filters["repr"] = repr
    env.filters["pascal"] = _to_pascal_case
    env.filters["escape_doc"] = _escape_docstring
    template = env.get_template(template_name)

    # Auto-extract typing imports and extra imports if tools are provided
    if "tools" in kwargs:
        tools = kwargs["tools"]
        if isinstance(tools, list):
            if "typing_imports" not in kwargs:
                kwargs = dict(kwargs, typing_imports=_extract_typing_imports(tools))
            if "extra_imports" not in kwargs:
                kwargs = dict(kwargs, extra_imports=_collect_extra_imports(tools))

    return template.render(**kwargs)
