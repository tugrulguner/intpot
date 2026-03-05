"""Shared data models for the inspect -> normalize -> generate pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(Enum):
    MCP = "mcp"
    CLI = "cli"
    API = "api"


_SENTINEL = object()


@dataclass
class ParameterInfo:
    name: str
    type_annotation: str = "str"
    default: Any = _SENTINEL  # _SENTINEL means required (no default)
    description: str = ""

    @property
    def required(self) -> bool:
        return self.default is _SENTINEL


@dataclass
class ToolInfo:
    name: str
    description: str = ""
    parameters: list[ParameterInfo] = field(default_factory=list)
    return_type: str = "str"
    http_method: str = "POST"
