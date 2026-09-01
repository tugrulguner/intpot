"""Abstract base generator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from intpot.core.models import ApplicationSchema, ToolInfo, ToolSchema

GenerationInput = ApplicationSchema | Sequence[ToolInfo]
RenderableTool = ToolInfo | ToolSchema


def generation_context(
    source: GenerationInput,
    *,
    default_name: str,
) -> tuple[Sequence[RenderableTool], str]:
    """Normalize canonical and compatibility inputs for a generator."""
    if isinstance(source, ApplicationSchema):
        return source.tools, source.name
    return tuple(ToolSchema.from_info(tool) for tool in source), default_name


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, source: GenerationInput) -> str:
        """Generate source from a canonical schema or compatibility tool sequence."""
        ...
