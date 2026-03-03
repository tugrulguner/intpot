"""Generate a Typer CLI app from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import BaseGenerator
from intpot.core.models import ToolInfo


class CLIGenerator(BaseGenerator):
    def generate(self, tools: list[ToolInfo]) -> str:
        return render_template("cli_app.py.j2", tools=tools)
