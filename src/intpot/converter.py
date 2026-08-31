"""Python API for intpot: load sources and convert programmatically."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from intpot.core.detector import SourceImportError, detect_instance, detect_source
from intpot.core.models import ApplicationSchema, SourceType, ToolInfo


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


def _inspect_tools(source_type: SourceType, app_instance: Any) -> list[ToolInfo]:
    """Inspect an app instance into the compatibility tool models."""
    if source_type == SourceType.MCP:
        from intpot.core.inspectors.mcp import MCPInspector

        return MCPInspector().inspect(app_instance)
    if source_type == SourceType.CLI:
        from intpot.core.inspectors.cli import CLIInspector

        return CLIInspector().inspect(app_instance)

    from intpot.core.inspectors.api import APIInspector

    return APIInspector().inspect(app_instance)


def _application_name(
    source_type: SourceType,
    app_instance: Any,
    source_path: Path | None = None,
) -> str:
    """Read a stable human-facing name using each framework's own semantics."""
    candidate: Any = None
    if source_type == SourceType.MCP:
        candidate = getattr(app_instance, "name", None)
    elif source_type == SourceType.API:
        title = getattr(app_instance, "title", None)
        candidate = title if title != "FastAPI" else None
    elif source_type == SourceType.CLI:
        candidate = getattr(getattr(app_instance, "info", None), "name", None)
        if not isinstance(candidate, str) or not candidate:
            candidate = getattr(app_instance, "name", None)

    if isinstance(candidate, str) and candidate:
        return candidate
    if source_path is not None:
        return source_path.stem
    return source_type.value


def compile_app(
    source_type: SourceType,
    app_instance: Any,
    *,
    source_path: Path | None = None,
) -> ApplicationSchema:
    """Compile a framework application into Intpot's canonical schema."""
    return ApplicationSchema.from_tools(
        name=_application_name(source_type, app_instance, source_path),
        source_type=source_type,
        tools=_inspect_tools(source_type, app_instance),
        source_path=source_path,
    )


def inspect_app(source_type: SourceType, app_instance: Any) -> list[ToolInfo]:
    """Inspect an app and return detached compatibility tool definitions."""
    return compile_app(source_type, app_instance).to_tools()


def _prepare_tools_for_target(
    source_type: SourceType, tools: list[ToolInfo], target: SourceType
) -> list[ToolInfo]:
    """Validate and transform an inspected tool snapshot for a target."""
    from intpot.core.transforms import transform_tools

    if source_type == SourceType.API and target in (SourceType.CLI, SourceType.MCP):
        _guard_fastapi_dependencies(tools)
    return transform_tools(tools, source_type, target)


def project_schema(
    schema: ApplicationSchema,
    target: SourceType,
) -> ApplicationSchema:
    """Project a canonical schema into target-specific immutable semantics."""
    tools = _prepare_tools_for_target(
        schema.source_type,
        schema.to_tools(),
        target,
    )
    return ApplicationSchema.from_tools(
        name=schema.name,
        source_type=schema.source_type,
        tools=tools,
        source_path=schema.source_path,
        target_type=target,
    )


def tools_for_target(
    source_type: SourceType, app_instance: Any, target: SourceType
) -> list[ToolInfo]:
    """Inspect an app and prepare tools for a target framework."""
    schema = compile_app(source_type, app_instance)
    return project_schema(schema, target).to_tools()


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
    def schema(self) -> ApplicationSchema:
        """Compile the app into a stable immutable semantic snapshot."""
        return compile_app(
            self.source_type,
            self.app,
            source_path=self.source_path,
        )

    @property
    def tools(self) -> list[ToolInfo]:
        """Return detached compatibility models from the compiled schema."""
        return self.schema.to_tools()

    def _tools_for(self, target: SourceType) -> list[ToolInfo]:
        """Return tools transformed for the target framework."""
        return self.project(target).to_tools()

    def project(self, target: str | SourceType) -> ApplicationSchema:
        """Return an immutable target projection of the compiled application."""
        if isinstance(target, str):
            try:
                target = SourceType(target)
            except ValueError:
                raise ValueError(
                    f"Unknown target '{target}', expected: cli, mcp, api"
                ) from None
        if target not in (SourceType.CLI, SourceType.MCP, SourceType.API):
            raise ValueError(
                f"Unknown target '{target.value}', expected: cli, mcp, api"
            )
        if target == self.source_type:
            raise ValueError(
                f"Source is already a {self.source_type.value.upper()} app"
            )
        return project_schema(self.schema, target)

    def to_cli(self) -> str:
        """Generate Typer CLI code."""
        if self.source_type == SourceType.CLI:
            raise ValueError("Source is already a CLI app")
        from intpot.core.generators.cli import CLIGenerator

        return CLIGenerator().generate(self.project(SourceType.CLI))

    def to_mcp(self) -> str:
        """Generate FastMCP server code."""
        if self.source_type == SourceType.MCP:
            raise ValueError("Source is already an MCP server")
        from intpot.core.generators.mcp import MCPGenerator

        return MCPGenerator().generate(self.project(SourceType.MCP))

    def to_api(self) -> str:
        """Generate FastAPI app code."""
        if self.source_type == SourceType.API:
            raise ValueError("Source is already an API app")
        from intpot.core.generators.api import APIGenerator

        return APIGenerator().generate(self.project(SourceType.API))

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
