"""Immutable target projections shared by generators and live builders."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from intpot.core.models import (
    ApplicationSchema,
    ParameterPlacement,
    ParamSource,
    SourceType,
)


class ParameterContract(Protocol):
    """The compatibility and canonical fields needed to resolve placement."""

    @property
    def required(self) -> bool: ...

    @property
    def param_source(self) -> ParamSource | None: ...

    @property
    def placement(self) -> ParameterPlacement | None: ...


class ToolNameContract(Protocol):
    """The compatibility and canonical fields needed to expose a tool name."""

    @property
    def name(self) -> str: ...

    @property
    def interface_name(self) -> str | None: ...


_API_PLACEMENTS = {
    ParamSource.body: ParameterPlacement.API_BODY,
    ParamSource.query: ParameterPlacement.API_QUERY,
    ParamSource.header: ParameterPlacement.API_HEADER,
    ParamSource.path: ParameterPlacement.API_PATH,
}


def resolve_tool_interface_name(tool: ToolNameContract, target: SourceType) -> str:
    """Resolve the framework-visible name without changing its Python binding."""
    if target not in (SourceType.CLI, SourceType.API, SourceType.MCP):
        raise ValueError(f"Tool names are not defined for target {target.value!r}")
    return tool.interface_name or tool.name


def project_tool_names(
    schema: ApplicationSchema, target: SourceType
) -> ApplicationSchema:
    """Return a target schema with framework-visible tool names made explicit."""
    changed_tools = False
    projected_tools = []
    for tool in schema.tools:
        interface_name = resolve_tool_interface_name(tool, target)
        route_path = (
            tool.route_path or f"/{interface_name}"
            if target is SourceType.API
            else tool.route_path
        )
        if tool.interface_name == interface_name and tool.route_path == route_path:
            projected_tools.append(tool)
        else:
            projected_tools.append(
                replace(tool, interface_name=interface_name, route_path=route_path)
            )
            changed_tools = True

    if not changed_tools and schema.target_type is target:
        return schema
    return replace(schema, tools=tuple(projected_tools), target_type=target)


def resolve_parameter_placement(
    parameter: ParameterContract, target: SourceType
) -> ParameterPlacement:
    """Resolve one parameter's explicit placement for a target framework."""
    if target is SourceType.CLI:
        return (
            ParameterPlacement.CLI_ARGUMENT
            if parameter.required
            else ParameterPlacement.CLI_OPTION
        )
    if target is SourceType.API:
        if parameter.param_source is not None:
            return _API_PLACEMENTS[parameter.param_source]
        placement = parameter.placement
        if placement in _API_PLACEMENTS.values():
            assert placement is not None
            return placement
        return ParameterPlacement.API_BODY
    if target is SourceType.MCP:
        return ParameterPlacement.MCP_PARAMETER
    raise ValueError(f"Parameter placement is not defined for target {target.value!r}")


def project_parameter_placement(
    schema: ApplicationSchema, target: SourceType
) -> ApplicationSchema:
    """Return a target schema with placement explicit and unchanged records shared."""
    changed_tools = False
    projected_tools = []
    for tool in schema.tools:
        changed_parameters = False
        projected_parameters = []
        for parameter in tool.parameters:
            placement = resolve_parameter_placement(parameter, target)
            if parameter.placement is placement:
                projected_parameters.append(parameter)
            else:
                projected_parameters.append(replace(parameter, placement=placement))
                changed_parameters = True
        if changed_parameters:
            projected_tools.append(
                replace(tool, parameters=tuple(projected_parameters))
            )
            changed_tools = True
        else:
            projected_tools.append(tool)

    if not changed_tools and schema.target_type is target:
        return schema
    return replace(schema, tools=tuple(projected_tools), target_type=target)
