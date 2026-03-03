"""Abstract base inspector."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from intpot.core.models import ToolInfo


class BaseInspector(ABC):
    @abstractmethod
    def inspect(self, app: Any) -> list[ToolInfo]:
        """Extract tool definitions from an app instance."""
        ...
