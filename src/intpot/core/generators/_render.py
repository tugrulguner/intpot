"""Shared Jinja2 rendering logic for generators."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def render_template(template_name: str, **kwargs: object) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    env.filters["repr"] = repr
    template = env.get_template(template_name)
    return template.render(**kwargs)
