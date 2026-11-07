"""Pure candidate identity metadata, never permission to execute a CLI callback."""

from __future__ import annotations

import hashlib
import inspect
import keyword
import marshal
import sys
import types
import unicodedata
import weakref
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from typing import Any, Optional, get_args

_CAPTURED: dict[int, tuple[weakref.ReferenceType[Any], weakref.ReferenceType[Any]]] = {}


def _identifier(value: Any) -> bool:
    return (
        type(value) is str
        and value.isidentifier()
        and not keyword.iskeyword(value)
        and unicodedata.normalize("NFKC", value) == value
    )


@dataclass(frozen=True, slots=True, weakref_slot=True)
class InformationalCallbackSpec:
    """Candidate identity only; existing callback refusal remains mandatory."""

    module: str
    export: str
    code_digest: str

    def __post_init__(self) -> None:
        if (
            type(self.module) is not str
            or not all(_identifier(part) for part in self.module.split("."))
            or not _identifier(self.export)
            or type(self.code_digest) is not str
            or len(self.code_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.code_digest)
        ):
            raise ValueError("Invalid informational callback identity")

    def to_dict(self) -> dict[str, str]:
        return {
            "module": self.module,
            "export": self.export,
            "code_digest": self.code_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InformationalCallbackSpec:
        if type(data) is not dict:
            raise TypeError("Callback identity must be plain data")
        return cls(**data)

    def resolve(self) -> types.FunctionType:
        """Check loaded identity/code only; do not import or call a callback."""
        owner = sys.modules.get(self.module)
        candidate = (
            vars(owner).get(self.export) if type(owner) is types.ModuleType else None
        )
        origin = _CAPTURED.get(id(self))
        if origin is not None and origin[0]() is self and origin[1]() is not candidate:
            raise TypeError("Callback export identity changed since inspection")
        current = capture_informational_callback(candidate)
        if current != self:
            raise TypeError("Callback export or code changed since inspection")
        assert type(candidate) is types.FunctionType
        return candidate


def _bool_annotation(annotation: Any) -> bool:
    if annotation is bool:
        return True
    if type(annotation) is str:
        return annotation.replace(" ", "") in (
            "bool",
            "bool|None",
            "None|bool",
            "Optional[bool]",
            "typing.Optional[bool]",
        )
    if type(annotation) is types.UnionType:
        args = annotation.__args__
        return len(args) == 2 and all(a is bool or a is type(None) for a in args)
    # typing.Optional has a builtin typing implementation, not arbitrary hooks.
    if type(annotation) is type(Optional[bool]):  # noqa: UP045 - detect legacy typing object, not PEP 604
        args = get_args(annotation)
        return len(args) == 2 and all(a is bool or a is type(None) for a in args)
    return False


def _callback_bool_annotation(annotation: Any, callback: types.FunctionType) -> bool:
    if not _bool_annotation(annotation):
        return False
    if type(annotation) is not str:
        return True
    namespace, builtin_namespace = callback.__globals__, callback.__builtins__
    if type(namespace) is not dict or type(builtin_namespace) is not dict:
        return False
    if namespace.get("bool", builtin_namespace.get("bool")) is not bool:
        return False
    text = annotation.replace(" ", "")
    if text == "Optional[bool]":
        return namespace.get("Optional") is Optional
    if text == "typing.Optional[bool]":
        owner = namespace.get("typing")
        return (
            type(owner) is types.ModuleType and vars(owner).get("Optional") is Optional
        )
    return True


def capture_parameter_informational_callback(
    annotation: Any,
    metadata: Any,
    default: Any,
    *,
    automatic_envvar: bool = False,
    context_default: bool = False,
    unsupported_context: bool = False,
) -> InformationalCallbackSpec | None:
    """Capture original ordinary OptionInfo only; preserve refusal independently."""
    from typer.models import OptionInfo

    if type(metadata) is not OptionInfo or not _bool_annotation(annotation):
        return None
    data = vars(metadata)
    if automatic_envvar or context_default or unsupported_context:
        return None
    if any(
        data.get(name) is not None
        for name in ("envvar", "default_factory", "parser", "click_type")
    ):
        return None
    prompt = data.get("prompt")
    if prompt is not None and prompt is not False:
        return None
    flag_value = data.get("flag_value")
    if flag_value is not None and flag_value is not True:
        return None
    if data.get("is_eager") is not True or (
        default is not False and default is not None
    ):
        return None
    return capture_informational_callback(data.get("callback"))


def capture_informational_callback(callback: Any) -> InformationalCallbackSpec | None:
    """Capture call shape/identity, not purity, effects or information semantics."""
    if type(callback) is not types.FunctionType:
        return None
    if type(callback.__module__) is not str or type(callback.__name__) is not str:
        return None
    namespace = vars(callback)
    if (
        callback.__closure__ is not None
        or callback.__qualname__ != callback.__name__
        or inspect.iscoroutinefunction(callback)
        or inspect.isgeneratorfunction(callback)
        or "__wrapped__" in namespace
        or "__signature__" in namespace
        or getattr(callback, "__annotate__", None) is not None
        or type(callback.__annotations__) is not dict
    ):
        return None
    owner = sys.modules.get(callback.__module__)
    if type(owner) is not types.ModuleType:
        return None
    module_data = vars(owner)
    spec = module_data.get("__spec__")
    if (
        type(module_data.get("__package__")) is not str
        or not module_data["__package__"]
        or type(spec) is not ModuleSpec
        or vars(spec).get("name") != callback.__module__
        or module_data.get(callback.__name__) is not callback
    ):
        return None
    parameters = tuple(
        inspect.signature(
            callback, follow_wrapped=False, eval_str=False
        ).parameters.values()
    )
    if (
        len(parameters) != 1
        or parameters[0].kind
        not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        or not _callback_bool_annotation(parameters[0].annotation, callback)
    ):
        return None
    try:
        digest = hashlib.sha256(marshal.dumps(callback.__code__)).hexdigest()
        result = InformationalCallbackSpec(
            callback.__module__, callback.__name__, digest
        )
    except (TypeError, ValueError):
        return None
    key = id(result)

    def forget(ref: weakref.ReferenceType[Any]) -> None:
        entry = _CAPTURED.get(key)
        if entry is not None and entry[0] is ref:
            _CAPTURED.pop(key, None)

    _CAPTURED[key] = (weakref.ref(result, forget), weakref.ref(callback))
    return result
