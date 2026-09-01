"""Generate a Typer CLI app from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import (
    BaseGenerator,
    GenerationInput,
    generation_context,
)


class CLIGenerator(BaseGenerator):
    def generate(self, source: GenerationInput) -> str:
        tools, app_name = generation_context(source, default_name="")
        return render_template("cli_app.py.j2", tools=tools, app_name=app_name)
