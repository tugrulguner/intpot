"""Canonical opt-in policy qualification, shared by projection and generators."""

from __future__ import annotations

from dataclasses import replace

from intpot.core.callbacks import UnsupportedCLIParameterCallbackError
from intpot.core.informational_policy import qualify_informational_callback
from intpot.core.models import ApplicationSchema, SourceType

INFORMATIONAL_POLICY = "exclusive-informational"


def qualify_informational_schema(
    schema: ApplicationSchema, policy: str, *, strict: bool = True
) -> ApplicationSchema:
    """Verify every callback before returning an independent policy-bearing snapshot."""
    if type(policy) is not str or policy != INFORMATIONAL_POLICY:
        raise ValueError("Unknown callback policy")
    if schema.source_type != SourceType.CLI or schema.target_type == SourceType.CLI:
        raise ValueError(
            "Informational callback policy requires CLI-to-API/MCP conversion"
        )
    states: dict[int, bool] = {}
    for tool in schema.tools:
        for parameter in tool.parameters:
            spec = parameter.informational_callback
            if parameter.unsupported_callback and spec is None:
                if not strict:
                    states[id(parameter)] = True
                    continue
                raise UnsupportedCLIParameterCallbackError(
                    f"Cannot convert CLI parameter callback for {tool.name}.{parameter.name}: "
                    "no verified informational metadata"
                )
            if spec is not None:
                try:
                    qualify_informational_callback(spec)
                except (TypeError, ValueError) as error:
                    if not strict:
                        states[id(parameter)] = True
                        continue
                    raise UnsupportedCLIParameterCallbackError(
                        f"Cannot convert CLI parameter callback for {tool.name}.{parameter.name}: "
                        "informational source proof failed"
                    ) from error
            states[id(parameter)] = False
    return replace(
        schema,
        callback_policy=policy,
        tools=tuple(
            replace(
                tool,
                parameters=tuple(
                    replace(
                        parameter,
                        unsupported_callback=states[id(parameter)],
                    )
                    for parameter in tool.parameters
                ),
            )
            for tool in schema.tools
        ),
    )
