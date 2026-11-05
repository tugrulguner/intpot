"""Detached descriptions of the bounded, importable string-enum subset."""

from __future__ import annotations

import keyword
import sys
import types
import unicodedata
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, EnumType, StrEnum
from typing import Annotated, Any, Union, cast, get_args, get_origin


def _identifier(value: str) -> bool:
    # Python normalizes identifier tokens; runtime Enum names retain exact spelling.
    return (
        type(value) is str
        and value.isidentifier()
        and not keyword.iskeyword(value)
        and unicodedata.normalize("NFKC", value) == value
    )


# Live capture evidence stays outside immutable/serialized metadata. Key by object
# identity, not dataclass equality: fresh captures may describe different classes
# with equal member data. Weak references retain neither snapshots nor classes.
_CAPTURED_ENUMS: dict[
    int, tuple[weakref.ReferenceType[StringEnumSpec], weakref.ReferenceType[type[Enum]]]
] = {}


def _remember_enum(spec: StringEnumSpec, candidate: type[Enum]) -> None:
    key = id(spec)

    def discard(reference: weakref.ReferenceType[StringEnumSpec]) -> None:
        entry = _CAPTURED_ENUMS.get(key)
        if entry is not None and entry[0] is reference:
            _CAPTURED_ENUMS.pop(key, None)

    _CAPTURED_ENUMS[key] = (weakref.ref(spec, discard), weakref.ref(candidate))


@dataclass(frozen=True, slots=True, weakref_slot=True)
class StringEnumSpec:
    module: str
    name: str
    members: tuple[tuple[str, str], ...]
    nullable: bool = False
    many: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.module) is not str
            or not self.module
            or not all(_identifier(p) for p in self.module.split("."))
            or not _identifier(self.name)
        ):
            raise ValueError("Invalid string-enum reference")
        members = tuple(tuple(pair) for pair in self.members)
        if not members or any(
            len(p) != 2 or not _identifier(p[0]) or type(p[1]) is not str
            for p in members
        ):
            raise ValueError("Invalid string-enum members")
        if len({p[0] for p in members}) != len(members) or len(
            {p[1] for p in members}
        ) != len(members):
            raise ValueError("String-enum aliases are not supported")
        if type(self.nullable) is not bool:
            raise ValueError("Invalid enum nullability")
        if type(self.many) is not bool:
            raise ValueError("Unsupported enum collection shape")
        object.__setattr__(self, "members", members)

    @property
    def key(self) -> str:
        return f"enum:{self.module}.{self.name}"

    def alias(self, aliases: Mapping[str, str]) -> str:
        alias = aliases.get(self.key, f"_intpot_enum_{self.name}")
        if not _identifier(alias):
            raise ValueError("Invalid string-enum import alias")
        return alias

    def import_source(self, aliases: Mapping[str, str]) -> str:
        self.resolve()
        return f"from {self.module} import {self.name} as {self.alias(aliases)}"

    def resolve(self) -> type[Enum]:
        owner = sys.modules.get(self.module)
        candidate = vars(owner).get(self.name) if owner is not None else None
        origin = _CAPTURED_ENUMS.get(id(self))
        if origin is not None and origin[0]() is self and origin[1]() is not candidate:
            raise TypeError("String-enum export identity changed since inspection")
        current = capture_string_enum(candidate, nullable=self.nullable, many=self.many)
        if current != self:
            raise TypeError("String-enum export or members changed since inspection")
        return cast(type[Enum], candidate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "name": self.name,
            "members": [list(pair) for pair in self.members],
            "nullable": self.nullable,
            **({"many": True} if self.many else {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StringEnumSpec:
        # Deliberately data-only: never import a module or resolve an export here.
        return cls(**data)


@dataclass(frozen=True, slots=True)
class StringEnumDefault:
    enum: StringEnumSpec
    member: str

    def __post_init__(self) -> None:
        if self.member not in dict(self.enum.members):
            raise ValueError("Unknown string-enum default member")

    def to_dict(self) -> dict[str, Any]:
        return {"enum": self.enum.to_dict(), "member": self.member}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StringEnumDefault:
        return cls(StringEnumSpec.from_dict(data["enum"]), data["member"])


def capture_string_enum(
    candidate: Any, *, nullable: bool = False, many: bool = False
) -> StringEnumSpec:
    if type(candidate) is not EnumType or candidate.__bases__ not in (
        (str, Enum),
        (StrEnum,),
    ):
        raise TypeError("Only ordinary importable string enums are supported")
    namespace = vars(candidate)
    for name in (
        "_missing_",
        "value",
        "name",
        "__getattr__",
        "__init__",
        "__getattribute__",
        "__get_pydantic_core_schema__",
        "__get_pydantic_json_schema__",
    ):
        if name in namespace:
            raise TypeError("Custom string-enum behavior is not supported")
    if namespace.get("_new_member_") not in (
        str.__new__,
        vars(StrEnum).get("_new_member_"),
    ):
        raise TypeError("Custom string-enum constructors are not supported")
    module_name = candidate.__module__
    owner = sys.modules.get(module_name)
    if (
        owner is None
        or not vars(owner).get("__package__")
        or candidate.__qualname__ != candidate.__name__
        or vars(owner).get(candidate.__name__) is not candidate
        or vars(owner).get("__spec__") is None
        or vars(vars(owner)["__spec__"]).get("name") != module_name
    ):
        raise TypeError("String enum must be a loaded module-level package export")
    for name in ("__str__", "__repr__", "__format__"):
        if name in namespace and namespace[name] not in (
            getattr(Enum, name),
            getattr(str, name),
            getattr(StrEnum, name),
        ):
            raise TypeError("Custom string-enum methods are not supported")
    spec = StringEnumSpec(
        module_name,
        candidate.__name__,
        tuple(
            (name, vars(member)["_value_"])
            for name, member in candidate.__members__.items()
        ),
        nullable,
        many,
    )
    _remember_enum(spec, cast(type[Enum], candidate))
    return spec


def annotation_string_enum(annotation: Any) -> StringEnumSpec | None:
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    nullable = False
    if get_origin(annotation) in (types.UnionType, Union):
        args = get_args(annotation)
        if len(args) == 2 and type(None) in args:
            annotation = next(a for a in args if a is not type(None))
            nullable = True
    if get_origin(annotation) is list:
        arguments = get_args(annotation)
        if (
            len(arguments) == 1
            and isinstance(arguments[0], type)
            and issubclass(arguments[0], Enum)
        ):
            return capture_string_enum(arguments[0], nullable=nullable, many=True)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return capture_string_enum(annotation, nullable=nullable)
    for argument in get_args(annotation):
        if annotation_string_enum(argument) is not None:
            raise TypeError("Collection or compound enum annotations are not supported")
    return None


def enum_default(spec: StringEnumSpec, default: Any) -> Any:
    cls = spec.resolve()
    if spec.many:
        if default is None:
            return None
        if type(default) not in (list, tuple):
            raise TypeError("Enum collection default must be None or a sequence")
        return [_enum_member_default(spec, cls, value) for value in default]
    if default is None and spec.nullable:
        return None
    return _enum_member_default(spec, cls, default)


def _enum_member_default(
    spec: StringEnumSpec, cls: type[Enum], default: Any
) -> StringEnumDefault:
    if isinstance(default, cls):
        return StringEnumDefault(spec, default.name)
    if type(default) is str:
        members = [name for name, value in spec.members if value == default]
        if members:
            return StringEnumDefault(spec, members[0])
    raise TypeError("String-enum default does not match the declared enum")
