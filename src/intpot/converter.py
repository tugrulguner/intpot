"""Python API for intpot: load sources and convert programmatically."""

from __future__ import annotations

import ast
import builtins
import functools
from dataclasses import replace
from pathlib import Path
from typing import Any

from intpot.core.binding_chains import definition_dependency_paths
from intpot.core.callbacks import (
    UnsupportedCLIParameterCallbackError as UnsupportedCLIParameterCallbackError,
)
from intpot.core.callbacks import (
    guard_cli_parameter_callbacks,
)
from intpot.core.definition_bindings import annotation_missing, definition_time_missing
from intpot.core.detector import SourceImportError, detect_instance, detect_source
from intpot.core.generators._render import _body_global_names
from intpot.core.models import ApplicationSchema, SourceType, ToolInfo
from intpot.core.numeric_ranges import (
    UnsupportedAPINumericRangeError as UnsupportedAPINumericRangeError,
)
from intpot.core.numeric_ranges import (
    UnsupportedCLINumericRangeError as UnsupportedCLINumericRangeError,
)
from intpot.core.numeric_ranges import (
    UnsupportedMCPNumericRangeError as UnsupportedMCPNumericRangeError,
)
from intpot.core.numeric_ranges import (
    guard_api_numeric_ranges,
    guard_cli_numeric_ranges,
    guard_mcp_numeric_ranges,
)
from intpot.core.projections import (
    project_parameter_aliases,
    project_parameter_placement,
    project_tool_names,
)
from intpot.core.provenance import location_dict
from intpot.core.reference_locations import body_reference_locations


class UnsupportedFastAPIDependencyError(Exception):
    """Raised when FastAPI dependency injection cannot be converted safely."""


def assess_schema(schema: ApplicationSchema) -> dict[str, Any]:
    """Assess known refusals, body recovery and bindings, not complete fidelity."""
    missing = [tool.name for tool in schema.tools if tool.function_body is None]
    refusal_diagnostics: list[dict[str, Any]] = []
    skipped_targets: set[SourceType] = set()
    for tool in schema.tools:
        for parameter in tool.parameters:
            if parameter.unsupported_callback:
                for target in (SourceType.API, SourceType.MCP):
                    if target == schema.source_type:
                        continue
                    skipped_targets.add(target)
                    refusal_diagnostics.append(
                        {
                            "code": "unsupported_cli_parameter_callback",
                            "tool": tool.name,
                            "parameter": parameter.name,
                            "target": target.value,
                            "source_location": location_dict(tool.source_location),
                            "message": f"CLI callback for parameter {parameter.name!r} cannot be preserved when converting to {target.value}.",
                            "consequence": "Source validation or parameter transformation would be lost without equivalent implementation; conversion is refused.",
                            "reference_analysis": "skipped_due_to_refusal",
                            "suggested_action": "Reimplement the callback's validation or transformation in the target application.",
                        }
                    )
            if parameter.unsupported_numeric_range:
                for target in (SourceType.CLI, SourceType.API, SourceType.MCP):
                    if target == schema.source_type:
                        continue
                    skipped_targets.add(target)
                    refusal_diagnostics.append(
                        {
                            "code": "unsupported_cli_numeric_range",
                            "tool": tool.name,
                            "parameter": parameter.name,
                            "target": target.value,
                            "source_location": location_dict(tool.source_location),
                            "message": f"CLI numeric range for parameter {parameter.name!r} cannot be preserved when converting to {target.value}.",
                            "consequence": "Source validation or clamping would be lost; conversion is refused.",
                            "reference_analysis": "skipped_due_to_refusal",
                            "suggested_action": "Implement equivalent validation/transformation explicitly or use finite inclusive non-clamping bounds.",
                        }
                    )
            if parameter.unsupported_api_numeric_range:
                for target in (SourceType.CLI, SourceType.API, SourceType.MCP):
                    if target == schema.source_type:
                        continue
                    skipped_targets.add(target)
                    refusal_diagnostics.append(
                        {
                            "code": "unsupported_api_numeric_range",
                            "tool": tool.name,
                            "parameter": parameter.name,
                            "target": target.value,
                            "source_location": location_dict(tool.source_location),
                            "message": f"API numeric validation for parameter {parameter.name!r} cannot be preserved when converting to {target.value}.",
                            "consequence": "Source validation would be lost; conversion is refused.",
                            "reference_analysis": "skipped_due_to_refusal",
                            "suggested_action": "Implement equivalent validation explicitly or use ordinary finite inclusive bounds with supported defaults.",
                        }
                    )
            if parameter.unsupported_mcp_numeric_range:
                for target in (SourceType.CLI, SourceType.API, SourceType.MCP):
                    if target == schema.source_type:
                        continue
                    skipped_targets.add(target)
                    refusal_diagnostics.append(
                        {
                            "code": "unsupported_mcp_numeric_range",
                            "tool": tool.name,
                            "parameter": parameter.name,
                            "target": target.value,
                            "source_location": location_dict(tool.source_location),
                            "message": f"MCP numeric validation for parameter {parameter.name!r} cannot be preserved when converting to {target.value}.",
                            "consequence": "Source validation would be lost; conversion is refused.",
                            "reference_analysis": "skipped_due_to_refusal",
                            "suggested_action": "Use ordinary finite inclusive bounds and supported defaults or implement equivalent validation explicitly.",
                        }
                    )
        if schema.source_type == SourceType.API and tool.dependencies:
            for target in (SourceType.CLI, SourceType.MCP):
                if target == schema.source_type:
                    continue
                skipped_targets.add(target)
                refusal_diagnostics.append(
                    {
                        "code": "unsupported_fastapi_dependency",
                        "tool": tool.name,
                        "target": target.value,
                        "source_location": location_dict(tool.source_location),
                        "route": {
                            "path": tool.route_path,
                            "operation_id": tool.operation_id,
                            "name": tool.interface_name,
                        },
                        "dependencies": list(tool.dependencies),
                        "message": f"FastAPI dependencies for tool {tool.name!r} cannot be represented when converting to {target.value}.",
                        "consequence": "Dependency execution, validation, and lifecycle behavior would be lost without equivalent implementation; conversion is refused.",
                        "reference_analysis": "skipped_due_to_refusal",
                        "suggested_action": "Implement equivalent dependency behavior explicitly in the target application.",
                    }
                )
    reference_diagnostics = _reference_diagnostics(
        schema,
        targets=[
            target
            for target in (SourceType.CLI, SourceType.API, SourceType.MCP)
            if target != schema.source_type and target not in skipped_targets
        ],
    )
    return {
        "body_recovery_complete": not missing,
        "missing_function_body": missing,
        "diagnostics": [
            {
                "code": "missing_function_body",
                "tool": name,
                "message": "Function source could not be recovered; output requires implementation.",
            }
            for name in missing
        ]
        + refusal_diagnostics
        + reference_diagnostics,
    }


def _binding_context(
    bindings: dict[str, list[str]],
    owners: set[str],
    *,
    before_definition: bool,
    source_location: tuple[str, int, int] | None = None,
    definition_locations: dict[str, tuple[str, int, int] | None] | None = None,
    dependency_paths: dict[str, list[str]] | None = None,
    body_locations: dict[str, dict[str, list[dict[str, Any]]] | None] | None = None,
) -> dict[str, Any]:
    """Describe emitted owners without inventing original-source coordinates."""
    references = [
        {
            "name": name,
            "generated_definition": owner,
            "reference_locations": (body_locations.get(owner) or {}).get(name)
            if body_locations is not None
            else None,
            "dependency_chain": dependency_paths.get(owner)
            if dependency_paths is not None
            else None,
            **(
                {"source_location": location_dict(definition_locations.get(owner))}
                if definition_locations is not None
                else {}
            ),
        }
        for owner in sorted(owners)
        for name in sorted(bindings.get(owner, []))
    ]
    names = ", ".join(sorted({item["name"] for item in references}))
    timing = (
        "before the affected generated definitions"
        if before_definition
        else "in the generated module before use"
    )
    return {
        "source_location": location_dict(source_location),
        "references": references,
        "suggested_action": (
            f"Import or define {names} {timing}, or adapt the source to the supported subset."
        ),
    }


def _reference_diagnostics(
    schema: ApplicationSchema,
    target: SourceType | None = None,
    *,
    targets: list[SourceType] | None = None,
) -> list[dict[str, Any]]:
    """Check retained bodies against bindings actually emitted for each target."""
    from intpot.core.generators._render import SupportDefinitionError, _private_aliases
    from intpot.core.generators.api import APIGenerator
    from intpot.core.generators.cli import CLIGenerator
    from intpot.core.generators.mcp import MCPGenerator
    from intpot.core.transforms import transform_schema

    generators = {
        SourceType.CLI: CLIGenerator,
        SourceType.API: APIGenerator,
        SourceType.MCP: MCPGenerator,
    }
    targets = (
        [target]
        if target is not None
        else targets
        if targets is not None
        else [candidate for candidate in generators if candidate != schema.source_type]
    )
    diagnostics: list[dict[str, Any]] = []
    for candidate in targets:
        projected = (
            schema
            if target is not None
            else project_tool_names(
                project_parameter_aliases(
                    project_parameter_placement(
                        transform_schema(schema, candidate), candidate
                    ),
                    candidate,
                ),
                candidate,
            )
        )
        try:
            code = generators[candidate]().generate(projected)
        except (ValueError, UnsupportedCLIParameterCallbackError) as exc:
            if target is not None:
                if isinstance(exc, SupportDefinitionError):
                    raise MissingBindingError(str(exc)) from None
                raise
            # A pre-existing rendering refusal is not a successful binding check.
            diagnostics.append(
                {
                    "code": "reference_analysis_unavailable",
                    "target": candidate.value,
                    "message": str(exc),
                }
            )
            continue
        module = ast.parse(code)
        definition_missing = definition_time_missing(module)
        # Standalone exports are normal file-loaded Python modules. Their loader
        # initializes these names without assignments in the emitted AST. Values
        # describe the generated module, not the original source or its resources;
        # arbitrary exec namespaces must provide their own module environment.
        available = set(dir(builtins)) | {
            "__name__",
            "__doc__",
            "__package__",
            "__loader__",
            "__spec__",
            "__file__",
            "__cached__",
            "__builtins__",
        }
        for node in module.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                available.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                available.update(
                    alias.asname
                    or (
                        alias.name.split(".", 1)[0]
                        if isinstance(node, ast.Import)
                        else alias.name
                    )
                    for alias in node.names
                    if alias.name != "*"
                )
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets_ = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                available.update(
                    child.id
                    for assignment in targets_
                    for child in ast.walk(assignment)
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
                )
        annotation_bindings = annotation_missing(module)
        functions = {
            node.name: node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        aliases = _private_aliases(projected.tools)
        for tool in projected.tools:
            owned_definitions = {tool.name, aliases.get(f"impl:{tool.name}", "")}
            for definition in tool.support_definitions:
                support = ast.parse(definition).body[0]
                if isinstance(support, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    owned_definitions.add(support.name)
            dependency_paths = definition_dependency_paths(
                functions, owned_definitions, tool.name, tool
            )
            definition_locations = None
            if tool.source_location is not None or tool.support_source_locations:
                definition_locations = {
                    aliases.get(f"impl:{tool.name}", ""): tool.source_location,
                    **dict(tool.support_source_locations),
                }
            definition_names = sorted(
                {
                    name
                    for owner in owned_definitions
                    for name in definition_missing.get(owner, [])
                }
            )
            if definition_names:
                diagnostics.append(
                    {
                        "code": "missing_definition_binding",
                        "tool": tool.name,
                        "target": candidate.value,
                        "names": definition_names,
                        **_binding_context(
                            definition_missing,
                            owned_definitions,
                            before_definition=True,
                            source_location=tool.source_location,
                            definition_locations=definition_locations,
                            dependency_paths=dependency_paths,
                        ),
                        "message": (
                            "Generated definition evaluates names before their bindings exist; "
                            "provide the required import/definition before the function "
                            "or adapt the source to the supported subset."
                        ),
                    }
                )
            annotation_names = sorted(
                {
                    name
                    for owner in owned_definitions
                    for name in annotation_bindings.get(owner, [])
                }
            )
            if annotation_names:
                diagnostics.append(
                    {
                        "code": "missing_annotation_binding",
                        "tool": tool.name,
                        "target": candidate.value,
                        "names": annotation_names,
                        **_binding_context(
                            annotation_bindings,
                            owned_definitions,
                            before_definition=False,
                            source_location=tool.source_location,
                            definition_locations=definition_locations,
                            dependency_paths=dependency_paths,
                        ),
                        "message": (
                            "Generated annotation refers to bindings absent from the emitted module; "
                            "provide the required import/definition or adapt the source to the supported subset."
                        ),
                    }
                )
            if not tool.function_body:
                continue
            implementation = functions[aliases[f"impl:{tool.name}"]]
            body = "\n".join(ast.unparse(node) for node in implementation.body)
            missing_names = (
                _body_global_names(replace(tool, function_body=body)) - available
            )
            body_bindings = {implementation.name: sorted(missing_names)}
            from intpot.core.models import ParameterSchema

            for definition in tool.support_definitions:
                support = ast.parse(definition).body[0]
                if not isinstance(support, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                arguments = [
                    *support.args.posonlyargs,
                    *support.args.args,
                    *support.args.kwonlyargs,
                ]
                if support.args.vararg:
                    arguments.append(support.args.vararg)
                if support.args.kwarg:
                    arguments.append(support.args.kwarg)
                helper = replace(
                    tool,
                    parameters=tuple(ParameterSchema(arg.arg) for arg in arguments),
                    function_body="\n".join(ast.unparse(node) for node in support.body),
                    is_async=isinstance(support, ast.AsyncFunctionDef),
                )
                helper_missing = _body_global_names(helper) - available
                body_bindings[support.name] = sorted(helper_missing)
                missing_names.update(helper_missing)
            names = sorted(missing_names)
            if names:
                digests = {
                    implementation.name: tool.source_digest,
                    **dict(tool.support_source_digests),
                }
                body_locations = {
                    owner: body_reference_locations(
                        functions[owner],
                        (definition_locations or {}).get(owner),
                        digests.get(owner),
                        tool.function_body if owner == implementation.name else None,
                    )
                    for owner in body_bindings
                    if body_bindings[owner] and owner in functions
                }
                diagnostics.append(
                    {
                        "code": "missing_binding",
                        "tool": tool.name,
                        "target": candidate.value,
                        "names": names,
                        **_binding_context(
                            body_bindings,
                            owned_definitions,
                            body_locations=body_locations,
                            before_definition=False,
                            source_location=tool.source_location,
                            definition_locations=definition_locations,
                            dependency_paths=dependency_paths,
                        ),
                        "message": "Retained implementation refers to bindings absent from generated output.",
                    }
                )
    return diagnostics


class MissingFunctionBodyError(ValueError):
    """Raised when conversion cannot recover a tool implementation."""


class MissingBindingError(ValueError):
    """Raised when retained code references unavailable module bindings."""


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
    if source_type == SourceType.PYTHON:
        from intpot.runtime import App

        if not isinstance(app_instance, App):
            raise ValueError("SourceType.PYTHON requires an intpot.App instance")
        return app_instance.tools
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
    if source_type in (SourceType.MCP, SourceType.PYTHON):
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
    guard_cli_parameter_callbacks(tools, target)
    return transform_tools(tools, source_type, target)


def project_schema(
    schema: ApplicationSchema,
    target: SourceType,
    *,
    allow_scaffold: bool = False,
) -> ApplicationSchema:
    """Project a canonical schema into target-specific immutable semantics."""
    from intpot.core.transforms import transform_schema

    if schema.source_type == SourceType.API and target in (
        SourceType.CLI,
        SourceType.MCP,
    ):
        _guard_fastapi_dependencies(schema.to_tools())
    guard_cli_parameter_callbacks(schema.tools, target)
    guard_cli_numeric_ranges(schema.tools)
    guard_api_numeric_ranges(schema.tools)
    guard_mcp_numeric_ranges(schema.tools)
    missing = [tool.name for tool in schema.tools if tool.function_body is None]
    if missing and not allow_scaffold:
        raise MissingFunctionBodyError(
            "Cannot convert tools whose function bodies could not be recovered: "
            + ", ".join(missing)
            + ". Pass allow_scaffold=True (CLI: --allow-scaffold) to emit NotImplementedError scaffolds."
        )
    if missing:
        schema = replace(
            schema,
            tools=tuple(
                replace(
                    tool,
                    function_body=(
                        "from builtins import NotImplementedError as _intpot_missing_body\n"
                        "raise _intpot_missing_body("
                        + repr(f"Scaffold: implement tool {tool.name}")
                        + ")"
                    ),
                )
                if tool.function_body is None
                else tool
                for tool in schema.tools
            ),
        )
    transformed = transform_schema(schema, target)
    projected = project_tool_names(
        project_parameter_aliases(
            project_parameter_placement(transformed, target), target
        ),
        target,
    )
    binding_errors = _reference_diagnostics(projected, target)
    if binding_errors:
        detail = "; ".join(
            f"{item['tool']}: {', '.join(item['names'])}" for item in binding_errors
        )
        raise MissingBindingError(
            "Cannot convert tools with missing bindings: " + detail
        )
    return projected


def tools_for_target(
    source_type: SourceType,
    app_instance: Any,
    target: SourceType,
    *,
    allow_scaffold: bool = False,
) -> list[ToolInfo]:
    """Inspect an app and prepare tools for a target framework."""
    schema = compile_app(source_type, app_instance)
    return project_schema(schema, target, allow_scaffold=allow_scaffold).to_tools()


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

    def assess(self) -> dict[str, Any]:
        """Report known refusals and per-target bindings, not complete fidelity."""
        return assess_schema(self.schema)

    @property
    def tools(self) -> list[ToolInfo]:
        """Return detached compatibility models from the compiled schema."""
        return self.schema.to_tools()

    def _tools_for(self, target: SourceType) -> list[ToolInfo]:
        """Return tools transformed for the target framework."""
        return self.project(target).to_tools()

    def project(
        self, target: str | SourceType, *, allow_scaffold: bool = False
    ) -> ApplicationSchema:
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
        return project_schema(self.schema, target, allow_scaffold=allow_scaffold)

    def to_cli(self, *, allow_scaffold: bool = False) -> str:
        """Generate Typer CLI code."""
        if self.source_type == SourceType.CLI:
            raise ValueError("Source is already a CLI app")
        from intpot.core.generators.cli import CLIGenerator

        return CLIGenerator().generate(
            self.project(SourceType.CLI, allow_scaffold=allow_scaffold)
        )

    def to_mcp(self, *, allow_scaffold: bool = False) -> str:
        """Generate FastMCP server code."""
        if self.source_type == SourceType.MCP:
            raise ValueError("Source is already an MCP server")
        from intpot.core.generators.mcp import MCPGenerator

        return MCPGenerator().generate(
            self.project(SourceType.MCP, allow_scaffold=allow_scaffold)
        )

    def to_api(self, *, allow_scaffold: bool = False) -> str:
        """Generate FastAPI app code."""
        if self.source_type == SourceType.API:
            raise ValueError("Source is already an API app")
        from intpot.core.generators.api import APIGenerator

        return APIGenerator().generate(
            self.project(SourceType.API, allow_scaffold=allow_scaffold)
        )

    def write(
        self,
        path: str | Path,
        target: str | SourceType,
        *,
        allow_scaffold: bool = False,
    ) -> Path:
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

        generators = {
            "cli": lambda: self.to_cli(allow_scaffold=allow_scaffold),
            "mcp": lambda: self.to_mcp(allow_scaffold=allow_scaffold),
            "api": lambda: self.to_api(allow_scaffold=allow_scaffold),
        }
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
