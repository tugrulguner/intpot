"""Abstract base generator."""

from __future__ import annotations

from abc import ABC, abstractmethod

from intpot.core.models import ToolInfo


class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, tools: list[ToolInfo]) -> str:
        """Generate source code from a list of ToolInfo."""
        ...
