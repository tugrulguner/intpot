"""Generate a FastAPI app from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import (
    BaseGenerator,
    GenerationInput,
    generation_context,
)
from intpot.core.models import SourceType


class APIGenerator(BaseGenerator):
    def generate(self, source: GenerationInput) -> str:
        schema = generation_context(
            source, default_name="FastAPI", target=SourceType.API
        )
        return render_template(
            "api_app.py.j2", tools=schema.tools, app_name=schema.name, schema=schema
        )
