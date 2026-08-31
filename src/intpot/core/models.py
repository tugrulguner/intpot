"""Shared data models for the inspect -> normalize -> generate pipeline."""

from __future__ import annotations

import base64
import copy
import json
import keyword
import re
from collections import deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import UUID


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


class _FrozenBytearray(bytes):
    """Immutable bytes that preserve a bytearray default's source representation."""

    def __repr__(self) -> str:
        return f"bytearray({bytes(self)!r})"


@dataclass(frozen=True, slots=True)
class _FrozenDeque:
    """Immutable snapshot of a deque and its maximum length."""

    items: tuple[Any, ...]
    maxlen: int | None

    def __iter__(self) -> Iterator[Any]:
        return iter(self.items)

    def __repr__(self) -> str:
        values = [_thaw_default(value) for value in self.items]
        suffix = f", maxlen={self.maxlen}" if self.maxlen is not None else ""
        return f"deque({values!r}{suffix})"


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
            {_thaw_default(key): _thaw_default(value) for key, value in self.entries}
        )


def _freeze_default(value: Any) -> Any:
    """Detach and recursively freeze supported Python parameter defaults."""
    if value is _SENTINEL:
        return value
    if isinstance(
        value,
        (
            _FrozenBytearray,
            _FrozenDeque,
            _FrozenDict,
            _FrozenList,
            _FrozenTuple,
            _FrozenSet,
        ),
    ):
        return value
    if isinstance(value, bytearray):
        return _FrozenBytearray(value)
    if isinstance(value, deque):
        return _FrozenDeque(
            tuple(_freeze_default(item) for item in value),
            value.maxlen,
        )
    if isinstance(value, dict):
        return _FrozenDict(
            tuple(
                (_freeze_default(key), _freeze_default(item))
                for key, item in value.items()
            )
        )
    if isinstance(value, list):
        return _FrozenList(_freeze_default(item) for item in value)
    if isinstance(value, tuple):
        return _FrozenTuple(_freeze_default(item) for item in value)
    if isinstance(value, set):
        return _FrozenSet(_freeze_default(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_freeze_default(item) for item in value)
    if value is None or value is Ellipsis or value is NotImplemented:
        return value
    if isinstance(
        value,
        (
            bool,
            int,
            float,
            complex,
            str,
            bytes,
            date,
            datetime,
            time,
            timedelta,
            Decimal,
            Enum,
            Fraction,
            Path,
            range,
            slice,
            UUID,
        ),
    ):
        return copy.deepcopy(value)
    raise TypeError(
        "Unsupported parameter default "
        f"{type(value).__module__}.{type(value).__qualname__}; "
        "use an immutable scalar or a supported container"
    )


def _thaw_default(value: Any) -> Any:
    """Return a detached value with the source container types restored."""
    if value is _SENTINEL:
        return value
    if isinstance(value, _FrozenBytearray):
        return bytearray(value)
    if isinstance(value, _FrozenDeque):
        return deque(
            (_thaw_default(item) for item in value.items),
            maxlen=value.maxlen,
        )
    if isinstance(value, _FrozenDict):
        return {_thaw_default(key): _thaw_default(item) for key, item in value.entries}
    if isinstance(value, _FrozenList):
        return [_thaw_default(item) for item in value]
    if isinstance(value, _FrozenTuple):
        return tuple(_thaw_default(item) for item in value)
    if isinstance(value, _FrozenSet):
        return {_thaw_default(item) for item in value}
    if isinstance(value, frozenset):
        return frozenset(_thaw_default(item) for item in value)
    return copy.deepcopy(value)


def _json_key(value: Any) -> str | int | float | bool | None:
    """Normalize a mapping key into a value accepted by the JSON encoder."""
    normalized = _json_default(value)
    if normalized is None or isinstance(normalized, (str, int, float, bool)):
        return normalized
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _json_default(value: Any) -> Any:
    """Normalize a frozen default into a deterministic JSON-compatible value."""
    if isinstance(value, _FrozenBytearray):
        return {
            "type": "bytearray",
            "base64": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if isinstance(value, _FrozenDeque):
        return {
            "type": "deque",
            "items": [_json_default(item) for item in value.items],
            "maxlen": value.maxlen,
        }
    if isinstance(value, _FrozenDict):
        return {_json_key(key): _json_default(item) for key, item in value.entries}
    if isinstance(value, (_FrozenList, _FrozenTuple, list, tuple)):
        return [_json_default(item) for item in value]
    if isinstance(value, (_FrozenSet, set, frozenset)):
        items = [_json_default(item) for item in value]
        items.sort(
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"))
        )
        return {
            "type": "frozenset" if type(value) is frozenset else "set",
            "items": items,
        }
    if isinstance(value, Enum):
        return {
            "type": "enum",
            "class": f"{type(value).__module__}.{type(value).__qualname__}",
            "name": value.name,
            "value": _json_default(value.value),
        }
    if isinstance(value, Path):
        return {"type": "path", "value": str(value)}
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "base64": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"type": "time", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"type": "timedelta", "seconds": value.total_seconds()}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, Fraction):
        return {
            "type": "fraction",
            "numerator": value.numerator,
            "denominator": value.denominator,
        }
    if isinstance(value, UUID):
        return {"type": "uuid", "value": str(value)}
    if isinstance(value, complex):
        return {"type": "complex", "real": value.real, "imag": value.imag}
    if isinstance(value, range):
        return {
            "type": "range",
            "start": value.start,
            "stop": value.stop,
            "step": value.step,
        }
    if isinstance(value, slice):
        return {
            "type": "slice",
            "start": _json_default(value.start),
            "stop": _json_default(value.stop),
            "step": _json_default(value.step),
        }
    if value is Ellipsis:
        return {"type": "ellipsis"}
    if value is NotImplemented:
        return {"type": "not-implemented"}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Unsupported JSON parameter default: {type(value).__qualname__}")


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
            result["default"] = _json_default(self.default)
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
