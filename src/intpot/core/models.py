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
    - Collapses runs of ``_`` into one
    - Prepends ``_`` if the name starts with a digit
    - Appends ``_`` if the name is a Python keyword
    - Returns ``_`` for empty / whitespace-only input

    Leading and trailing underscores are preserved: stripping them collapsed
    ``_name`` onto ``name``, so two distinct parameters could end up sharing an
    identifier in the generated code.
    """
    if not name or not name.strip():
        return "_"
    # Replace any character Python would not accept inside an identifier.
    # Tested per character rather than against [0-9a-zA-Z_]: Python 3 allows
    # non-ASCII letters, and mangling `café` into `caf_` both lost information
    # and invented collisions with a genuine `caf_`. `("a" + ch)` is what makes
    # this exact — it accepts `é` while still rejecting `²`, which is
    # alphanumeric but not valid in an identifier.
    name = "".join(ch if ("a" + ch).isidentifier() else "_" for ch in name)
    # Collapse consecutive underscores
    name = re.sub(r"_+", "_", name)
    if not name:
        return "_"
    # Prepend underscore if starts with digit
    if name[0].isdigit():
        name = f"_{name}"
    # Append underscore if it's a Python keyword
    if keyword.iskeyword(name):
        name = f"{name}_"
    return name


class ParamSource(str, Enum):
    body = "body"
    query = "query"
    header = "header"
    path = "path"

    @property
    def fastapi_class(self) -> str:
        """Return the exact FastAPI class name for this source."""
        return {
            ParamSource.body: "Body",
            ParamSource.query: "Query",
            ParamSource.header: "Header",
            ParamSource.path: "Path",
        }[self]


@dataclass
class ParameterInfo:
    name: str
    type_annotation: str = "str"
    default: Any = _SENTINEL  # _SENTINEL means required (no default)
    description: str = ""
    param_source: ParamSource | None = None

    def __post_init__(self) -> None:
        self.name = sanitize_identifier(self.name)

    @property
    def required(self) -> bool:
        return self.default is _SENTINEL


def deduplicate_identifiers(names: list[str]) -> list[str]:
    """Make a list of identifiers unique, preserving order and first occurrence.

    Sanitising is per-name, so distinct inputs can land on the same identifier:
    `a-b` and `a_b` both become `a_b`. Two parameters sharing a name is
    `SyntaxError: duplicate argument` in the generated function, so later
    collisions get a numeric suffix.
    """
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        candidate = name
        counter = 2
        while candidate in seen:
            candidate = f"{name}_{counter}"
            counter += 1
        seen.add(candidate)
        result.append(candidate)
    return result


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
        # Parameter names are sanitised individually, so two distinct source
        # names can arrive here already collapsed onto one identifier.
        unique = deduplicate_identifiers([p.name for p in self.parameters])
        for param, name in zip(self.parameters, unique, strict=True):
            param.name = name
