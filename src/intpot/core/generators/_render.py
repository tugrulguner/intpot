"""Shared Jinja2 rendering logic for generators."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


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


def render_template(template_name: str, **kwargs: object) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    env.filters["repr"] = repr
    env.filters["pascal"] = _to_pascal_case
    env.filters["escape_doc"] = _escape_docstring
    template = env.get_template(template_name)
    return template.render(**kwargs)
