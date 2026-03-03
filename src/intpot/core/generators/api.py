"""Generate a FastAPI app from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import BaseGenerator
from intpot.core.models import ToolInfo


class APIGenerator(BaseGenerator):
    def generate(self, tools: list[ToolInfo]) -> str:
        return render_template("api_app.py.j2", tools=tools)
