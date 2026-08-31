"""Shared data models for the inspect -> normalize -> generate pipeline."""

from __future__ import annotations

import copy
import keyword
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SourceType(Enum):
    PYTHON = "python"
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


class _FrozenList(tuple[Any, ...]):
    """Immutable list value that still renders as valid list source."""

    def __repr__(self) -> str:
        return repr([_thaw_default(value) for value in self])


class _FrozenTuple(tuple[Any, ...]):
    """Immutable tuple value with recursively thawed source representation."""

    def __repr__(self) -> str:
        return repr(tuple(_thaw_default(value) for value in self))


class _FrozenSet(frozenset[Any]):
    """Immutable set value that renders as a normal set literal."""

    def __repr__(self) -> str:
        return repr({_thaw_default(value) for value in self})


@dataclass(frozen=True)
class _FrozenDict(Mapping[Any, Any]):
    """Read-only mapping that preserves insertion order and nested values."""

    entries: tuple[tuple[Any, Any], ...]

    def __iter__(self) -> Iterator[Any]:
        return (key for key, _ in self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, key: Any) -> Any:
        for candidate, value in self.entries:
            if candidate == key:
                return value
        raise KeyError(key)

    def __repr__(self) -> str:
        return repr(
            {copy.deepcopy(key): _thaw_default(value) for key, value in self.entries}
        )


def _freeze_default(value: Any) -> Any:
    """Detach and recursively freeze common mutable Python defaults."""
    if value is _SENTINEL:
        return value
    if isinstance(value, (_FrozenDict, _FrozenList, _FrozenTuple, _FrozenSet)):
        return value
    if isinstance(value, dict):
        return _FrozenDict(
            tuple(
                (copy.deepcopy(key), _freeze_default(item))
                for key, item in value.items()
            )
        )
    if isinstance(value, list):
        return _FrozenList(_freeze_default(item) for item in value)
    if isinstance(value, tuple):
        return _FrozenTuple(_freeze_default(item) for item in value)
    if isinstance(value, set):
        return _FrozenSet(_freeze_default(item) for item in value)
    return copy.deepcopy(value)


def _thaw_default(value: Any) -> Any:
    """Return a detached value with the source container types restored."""
    if value is _SENTINEL:
        return value
    if isinstance(value, _FrozenDict):
        return {copy.deepcopy(key): _thaw_default(item) for key, item in value.entries}
    if isinstance(value, _FrozenList):
        return [_thaw_default(item) for item in value]
    if isinstance(value, _FrozenTuple):
        return tuple(_thaw_default(item) for item in value)
    if isinstance(value, _FrozenSet):
        return {_thaw_default(item) for item in value}
    return copy.deepcopy(value)


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


@dataclass(frozen=True, slots=True)
class ParameterSchema:
    """Immutable parameter semantics shared by every Intpot interface."""

    name: str
    type_annotation: str = "str"
    default: Any = _SENTINEL
    description: str = ""
    param_source: ParamSource | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", sanitize_identifier(self.name))
        object.__setattr__(self, "default", _freeze_default(self.default))

    @classmethod
    def from_info(cls, parameter: ParameterInfo) -> ParameterSchema:
        return cls(
            name=parameter.name,
            type_annotation=parameter.type_annotation,
            default=_freeze_default(parameter.default),
            description=parameter.description,
            param_source=parameter.param_source,
        )

    @property
    def required(self) -> bool:
        return self.default is _SENTINEL

    def to_info(self) -> ParameterInfo:
        """Return a mutable compatibility model for legacy integrations."""
        return ParameterInfo(
            name=self.name,
            type_annotation=self.type_annotation,
            default=_thaw_default(self.default),
            description=self.description,
            param_source=self.param_source,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a sentinel-free representation suitable for JSON encoding."""
        result: dict[str, Any] = {
            "name": self.name,
            "type_annotation": self.type_annotation,
            "description": self.description,
            "param_source": self.param_source.value if self.param_source else None,
            "required": self.required,
        }
        if not self.required:
            result["default"] = _thaw_default(self.default)
        return result


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """Immutable semantics for one callable interface operation."""

    name: str
    description: str = ""
    parameters: tuple[ParameterSchema, ...] = ()
    return_type: str = "str"
    http_method: str = "POST"
    function_body: str | None = None
    is_async: bool = False
    route_path: str | None = None
    dependencies: tuple[str, ...] = ()
    source_imports: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", sanitize_identifier(self.name))
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "source_imports", tuple(self.source_imports))

    @classmethod
    def from_info(cls, tool: ToolInfo) -> ToolSchema:
        return cls(
            name=tool.name,
            description=tool.description,
            parameters=tuple(ParameterSchema.from_info(p) for p in tool.parameters),
            return_type=tool.return_type,
            http_method=tool.http_method,
            function_body=tool.function_body,
            is_async=tool.is_async,
            route_path=tool.route_path,
            dependencies=tuple(tool.dependencies),
            source_imports=tuple(tool.source_imports),
        )

    def to_info(self) -> ToolInfo:
        """Return a mutable compatibility model for existing generators and callers."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=[p.to_info() for p in self.parameters],
            return_type=self.return_type,
            http_method=self.http_method,
            function_body=self.function_body,
            is_async=self.is_async,
            route_path=self.route_path,
            dependencies=list(self.dependencies),
            source_imports=list(self.source_imports),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the complete framework-neutral operation semantics."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "return_type": self.return_type,
            "http_method": self.http_method,
            "function_body": self.function_body,
            "is_async": self.is_async,
            "route_path": self.route_path,
            "dependencies": list(self.dependencies),
            "source_imports": list(self.source_imports),
        }


@dataclass(frozen=True, slots=True)
class ApplicationSchema:
    """Canonical immutable snapshot between inspection and every projection."""

    name: str
    source_type: SourceType
    tools: tuple[ToolSchema, ...]
    source_path: Path | None = None
    target_type: SourceType | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", tuple(self.tools))

    @classmethod
    def from_tools(
        cls,
        *,
        name: str,
        source_type: SourceType,
        tools: Iterable[ToolInfo],
        source_path: Path | None = None,
        target_type: SourceType | None = None,
    ) -> ApplicationSchema:
        resolved_path = source_path.resolve() if source_path is not None else None
        return cls(
            name=name,
            source_type=source_type,
            tools=tuple(ToolSchema.from_info(tool) for tool in tools),
            source_path=resolved_path,
            target_type=target_type,
        )

    def to_tools(self) -> list[ToolInfo]:
        """Return detached mutable models for backwards-compatible consumers."""
        return [tool.to_info() for tool in self.tools]

    def to_dict(self) -> dict[str, Any]:
        """Return a transparent, JSON-compatible view of the compiled app."""
        return {
            "name": self.name,
            "source_type": self.source_type.value,
            "source_path": str(self.source_path) if self.source_path else None,
            "target_type": self.target_type.value if self.target_type else None,
            "tools": [tool.to_dict() for tool in self.tools],
        }
