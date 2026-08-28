"""Python API for intpot: load sources and convert programmatically."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from intpot.core.detector import SourceImportError, detect_instance, detect_source
from intpot.core.models import SourceType, ToolInfo


class UnsupportedFastAPIDependencyError(Exception):
    """Raised when FastAPI dependency injection cannot be converted safely."""


def _guard_fastapi_dependencies(tools: list[ToolInfo]) -> None:
    unsupported = [tool for tool in tools if tool.dependencies]
    if not unsupported:
        return

    routes = "; ".join(
        f"route {tool.route_path or '<unknown>'} ({tool.name}): "
        f"{', '.join(tool.dependencies)}"
        for tool in unsupported
    )
    raise UnsupportedFastAPIDependencyError(
        "Cannot convert FastAPI dependencies to CLI or MCP safely: "
        f"{routes}. Depends/Security parameters, nested dependencies, and "
        "route/router/app-level dependencies are not supported yet; see issue #20."
    )


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


def _prepare_tools_for_target(
    source_type: SourceType, tools: list[ToolInfo], target: SourceType
) -> list[ToolInfo]:
    """Validate and transform an inspected tool snapshot for a target."""
    from intpot.core.transforms import transform_tools

    if source_type == SourceType.API and target in (SourceType.CLI, SourceType.MCP):
        _guard_fastapi_dependencies(tools)
    return transform_tools(tools, source_type, target)


def tools_for_target(
    source_type: SourceType, app_instance: Any, target: SourceType
) -> list[ToolInfo]:
    """Inspect an app and prepare tools for a target framework."""
    tools = inspect_app(source_type, app_instance)
    return _prepare_tools_for_target(source_type, tools, target)


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
        return _prepare_tools_for_target(self.source_type, self.tools, target)

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

    def write(
        self,
        path: str | Path,
        target: str | SourceType,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
    ) -> Path:
        """Generate code and write it to a file.

        Args:
            path: Output file path.
            target: Target framework — "cli", "mcp", "api" or a SourceType enum.
            encoding: Text encoding used for the generated source file.
            overwrite: Whether an existing output file may be replaced.

        Returns:
            The resolved Path that was written.

        Raises:
            FileExistsError: If ``overwrite`` is false and the output exists.
        """
        # Accept both strings and SourceType enum
        if isinstance(target, SourceType):
            target = target.value

        generators = {"cli": self.to_cli, "mcp": self.to_mcp, "api": self.to_api}
        if target not in generators:
            raise ValueError(f"Unknown target '{target}', expected: cli, mcp, api")
        out = Path(path)
        if out.exists() and not overwrite:
            raise FileExistsError(f"Output file already exists: {out}")
        code = generators[target]()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(code, encoding=encoding)
        return out.resolve()


def _missing_module_error(exc: ModuleNotFoundError) -> ModuleNotFoundError:
    """Point at the right extra, or hand the original error back unchanged.

    The top-level module is matched exactly. `"fastapi" in module` also matched
    a user's own missing `myfastapi_helper`, sending them to install
    intpot[api] — which would not have helped and hid the real cause.
    """
    top_level = (exc.name or "").split(".", 1)[0]
    if top_level == "fastmcp":
        return ModuleNotFoundError(
            "FastMCP is required for MCP support. "
            "Install it with: pip install intpot[mcp]",
            name=exc.name,
        )
    if top_level in ("fastapi", "uvicorn"):
        return ModuleNotFoundError(
            "FastAPI is required for API support. "
            "Install it with: pip install intpot[api]",
            name=exc.name,
        )
    return exc


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
    except SourceImportError as e:
        # detect_source wraps whatever the user's module raised so the CLI can
        # report it. This is the Python API, which documents ModuleNotFoundError
        # — unwrap it back so callers catching that keep working.
        original = e.__cause__
        if isinstance(original, ModuleNotFoundError):
            mapped = _missing_module_error(original)
            if mapped is original:
                # Handing the original back means exactly that. `raise original
                # from e` would set original.__cause__ = e while e.__cause__ is
                # already original, so the chain points at itself and anything
                # walking __cause__ loops forever.
                raise mapped from None
            raise mapped from original
        raise
    except ModuleNotFoundError as e:
        # The live-instance path: inspectors import fastmcp/fastapi themselves,
        # and that never goes through detect_source.
        raise _missing_module_error(e) from e
