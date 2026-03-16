"""Python API for intpot: load sources and convert programmatically."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from intpot.core.detector import detect_instance, detect_source
from intpot.core.models import SourceType, ToolInfo


def inspect_app(source_type: SourceType, app_instance: Any) -> list[ToolInfo]:
    """Inspect an app instance and return normalized tool definitions."""
    if source_type == SourceType.MCP:
        from intpot.core.inspectors.mcp import MCPInspector

        return MCPInspector().inspect(app_instance)
    if source_type == SourceType.CLI:
        from intpot.core.inspectors.cli import CLIInspector

        return CLIInspector().inspect(app_instance)

    from intpot.core.inspectors.api import APIInspector

    return APIInspector().inspect(app_instance)


class IntpotApp:
    """Wrapper around a detected app for programmatic conversion."""

    def __init__(
        self,
        source_type: SourceType,
        app_instance: Any,
        source_path: Path | None = None,
    ) -> None:
        self.source_type = source_type
        self.app = app_instance
        self.source_path = source_path

    def __repr__(self) -> str:
        src = f", source_path={self.source_path!r}" if self.source_path else ""
        return f"IntpotApp(source_type={self.source_type.value!r}{src})"

    @functools.cached_property
    def tools(self) -> list[ToolInfo]:
        """Inspect the app and return normalized tool definitions."""
        return inspect_app(self.source_type, self.app)

    def _tools_for(self, target: SourceType) -> list[ToolInfo]:
        """Return tools transformed for the target framework."""
        from intpot.core.transforms import transform_tools

        return transform_tools(self.tools, self.source_type, target)

    def to_cli(self) -> str:
        """Generate Typer CLI code."""
        if self.source_type == SourceType.CLI:
            raise ValueError("Source is already a CLI app")
        from intpot.core.generators.cli import CLIGenerator

        return CLIGenerator().generate(self._tools_for(SourceType.CLI))

    def to_mcp(self) -> str:
        """Generate FastMCP server code."""
        if self.source_type == SourceType.MCP:
            raise ValueError("Source is already an MCP server")
        from intpot.core.generators.mcp import MCPGenerator

        return MCPGenerator().generate(self._tools_for(SourceType.MCP))

    def to_api(self) -> str:
        """Generate FastAPI app code."""
        if self.source_type == SourceType.API:
            raise ValueError("Source is already an API app")
        from intpot.core.generators.api import APIGenerator

        return APIGenerator().generate(self._tools_for(SourceType.API))

    def write(self, path: str | Path, target: str | SourceType) -> Path:
        """Generate code and write it to a file.

        Args:
            path: Output file path.
            target: Target framework — "cli", "mcp", "api" or a SourceType enum.

        Returns:
            The resolved Path that was written.
        """
        # Accept both strings and SourceType enum
        if isinstance(target, SourceType):
            target = target.value

        generators = {"cli": self.to_cli, "mcp": self.to_mcp, "api": self.to_api}
        if target not in generators:
            raise ValueError(f"Unknown target '{target}', expected: cli, mcp, api")
        code = generators[target]()
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(code)
        return out.resolve()


def load(source: Any) -> IntpotApp:
    """Load a source for conversion.

    Args:
        source: A file path (str/Path) or a live app instance (FastMCP/Typer/FastAPI)

    Returns:
        IntpotApp wrapper with .to_cli(), .to_mcp(), .to_api() methods

    Raises:
        DetectionError: If the source type cannot be identified.
        ModuleNotFoundError: If required optional dependencies are missing
            (install intpot[mcp] or intpot[api]).
    """
    try:
        if isinstance(source, (str, Path)):
            path = Path(source)
            source_type, app_instance = detect_source(path)
            return IntpotApp(source_type, app_instance, source_path=path)

        source_type, app_instance = detect_instance(source)
        return IntpotApp(source_type, app_instance)
    except ModuleNotFoundError as e:
        module = e.name or ""
        if "fastmcp" in module:
            raise ModuleNotFoundError(
                "FastMCP is required for MCP support. "
                "Install it with: pip install intpot[mcp]"
            ) from e
        if "fastapi" in module:
            raise ModuleNotFoundError(
                "FastAPI is required for API support. "
                "Install it with: pip install intpot[api]"
            ) from e
        raise
