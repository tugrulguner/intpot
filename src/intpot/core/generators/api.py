"""Generate a FastAPI app from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import (
    BaseGenerator,
    GenerationInput,
    generation_context,
)


class APIGenerator(BaseGenerator):
    def generate(self, source: GenerationInput) -> str:
        tools, app_name = generation_context(source, default_name="FastAPI")
        return render_template("api_app.py.j2", tools=tools, app_name=app_name)
