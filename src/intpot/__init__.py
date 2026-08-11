"""intpot - serve Python tools as a CLI, API, or MCP server, or convert between them."""

from importlib.metadata import version

from intpot.converter import IntpotApp, inspect_app, load
from intpot.runtime import App

try:
    __version__ = version("intpot")
except Exception:
    # Not installed, or the installed metadata is unreadable — an incomplete
    # dist-info makes importlib raise TypeError rather than
    # PackageNotFoundError. Reporting a version is never worth failing an
    # import or a --version call over.
    __version__ = "0.0.0+unknown"

__all__ = ["App", "IntpotApp", "inspect_app", "load"]
