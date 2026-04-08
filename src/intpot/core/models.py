"""Shared data models for the inspect -> normalize -> generate pipeline."""

from __future__ import annotations

import keyword
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(Enum):
    MCP = "mcp"
    CLI = "cli"
    API = "api"


class ParameterSource(Enum):
    BODY = "body"
    QUERY = "query"
    HEADER = "header"
    PATH = "path"


class Agent(str, Enum):
    """Supported AI coding agents for skill installation."""

    claude = "claude"
    cursor = "cursor"
    windsurf = "windsurf"
    copilot = "copilot"
    cline = "cline"
    codex = "codex"


class _SentinelType:
    """Sentinel for 'no default value'. Singleton that survives deepcopy."""

    _instance = None

    def __new__(cls) -> _SentinelType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __deepcopy__(self, memo: dict) -> _SentinelType:
        return self

    def __copy__(self) -> _SentinelType:
        return self

    def __repr__(self) -> str:
        return "_SENTINEL"


_SENTINEL = _SentinelType()


def sanitize_identifier(name: str) -> str:
    """Convert an arbitrary string into a valid Python identifier.

    - Replaces invalid characters with ``_``
    - Prepends ``_`` if the name starts with a digit
    - Appends ``_`` if the name is a Python keyword
    - Returns ``_`` for empty / whitespace-only input
    """
    if not name or not name.strip():
        return "_"
    # Replace any character that is not alphanumeric or underscore
    name = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    # Collapse consecutive underscores
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        return "_"
    # Prepend underscore if starts with digit
    if name[0].isdigit():
        name = f"_{name}"
    # Append underscore if it's a Python keyword
    if keyword.iskeyword(name):
        name = f"{name}_"
    return name


@dataclass
class ParameterInfo:
    name: str
    type_annotation: str = "str"
    default: Any = _SENTINEL  # _SENTINEL means required (no default)
    description: str = ""
    source: ParameterSource = ParameterSource.BODY

    def __post_init__(self) -> None:
        self.name = sanitize_identifier(self.name)

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
    function_body: str | None = None
    is_async: bool = False
    route_path: str | None = None
    dependencies: list[str] = field(default_factory=list)
    source_imports: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = sanitize_identifier(self.name)
