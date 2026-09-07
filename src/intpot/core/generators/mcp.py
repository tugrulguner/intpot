"""Generate a FastMCP server from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import (
    BaseGenerator,
    GenerationInput,
    generation_context,
)


class MCPGenerator(BaseGenerator):
    def generate(self, source: GenerationInput) -> str:
        tools, app_name = generation_context(source, default_name="generated-server")
        return render_template("mcp_server.py.j2", tools=tools, app_name=app_name)
