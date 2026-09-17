"""Generate a FastMCP server from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import (
    BaseGenerator,
    GenerationInput,
    generation_context,
)
from intpot.core.models import SourceType


class MCPGenerator(BaseGenerator):
    def generate(self, source: GenerationInput) -> str:
        schema = generation_context(
            source, default_name="generated-server", target=SourceType.MCP
        )
        return render_template(
            "mcp_server.py.j2", tools=schema.tools, app_name=schema.name, schema=schema
        )
