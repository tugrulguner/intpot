"""intpot - Universal converter between CLI, MCP, and API interfaces."""

__version__ = "0.2.6"

from intpot.converter import IntpotApp, inspect_app, load

__all__ = ["IntpotApp", "inspect_app", "load"]
