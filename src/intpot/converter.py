"""Python API for intpot: load sources and convert programmatically."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intpot.core.detector import detect_instance, detect_source
from intpot.core.models import SourceType, ToolInfo


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

    def _get_tools(self) -> list[ToolInfo]:
        """Inspect the app and return normalized tool definitions."""
        if self.source_type == SourceType.MCP:
            from intpot.core.inspectors.mcp import MCPInspector

            return MCPInspector().inspect(self.app)
        if self.source_type == SourceType.CLI:
            from intpot.core.inspectors.cli import CLIInspector

            return CLIInspector().inspect(self.app)

        from intpot.core.inspectors.api import APIInspector

        return APIInspector().inspect(self.app)

    def to_cli(self) -> str:
        """Generate Typer CLI code."""
        if self.source_type == SourceType.CLI:
            raise ValueError("Source is already a CLI app")
        from intpot.core.generators.cli import CLIGenerator

        return CLIGenerator().generate(self._get_tools())

    def to_mcp(self) -> str:
        """Generate FastMCP server code."""
        if self.source_type == SourceType.MCP:
            raise ValueError("Source is already an MCP server")
        from intpot.core.generators.mcp import MCPGenerator

        return MCPGenerator().generate(self._get_tools())

    def to_api(self) -> str:
        """Generate FastAPI app code."""
        if self.source_type == SourceType.API:
            raise ValueError("Source is already an API app")
        from intpot.core.generators.api import APIGenerator

        return APIGenerator().generate(self._get_tools())

    def write(self, path: str | Path, target: str) -> Path:
        """Generate code and write it to a file.

        Args:
            path: Output file path.
            target: Target framework — "cli", "mcp", or "api".

        Returns:
            The resolved Path that was written.
        """
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
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        source_type, app_instance = detect_source(path)
        return IntpotApp(source_type, app_instance, source_path=path)

    source_type, app_instance = detect_instance(source)
    return IntpotApp(source_type, app_instance)
