"""Generate a FastMCP server from ToolInfo."""

from __future__ import annotations

from intpot.core.generators._render import render_template
from intpot.core.generators.base import BaseGenerator
from intpot.core.models import ToolInfo


class MCPGenerator(BaseGenerator):
    def generate(self, tools: list[ToolInfo]) -> str:
        return render_template("mcp_server.py.j2", tools=tools)
