"""Abstract base generator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from intpot.core.models import ApplicationSchema, SourceType, ToolInfo, ToolSchema
from intpot.core.projections import project_parameter_placement

GenerationInput = ApplicationSchema | Sequence[ToolInfo]
RenderableTool = ToolInfo | ToolSchema


def generation_context(
    source: GenerationInput,
    *,
    default_name: str,
    target: SourceType,
) -> ApplicationSchema:
    """Normalize canonical and compatibility inputs for a generator."""
    if isinstance(source, ApplicationSchema):
        schema = source
    else:
        schema = ApplicationSchema.from_tools(
            name=default_name,
            source_type=target,
            tools=source,
        )
    return project_parameter_placement(schema, target)


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, source: GenerationInput) -> str:
        """Generate source from a canonical schema or compatibility tool sequence."""
        ...
