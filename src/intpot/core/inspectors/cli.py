"""Extract commands from a Typer app instance."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import tokenize
import types
from enum import Enum
from typing import Annotated, Any, get_args, get_origin

from intpot.core.informational_callbacks import capture_parameter_informational_callback
from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_type_name,
)
from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo
from intpot.core.numeric_ranges import cli_numeric_range, cli_range_default
from intpot.core.provenance import callable_source_metadata, inspected_callable_metadata
from intpot.core.string_collections import cli_string_list
from intpot.core.string_enums import (
    StringEnumSpec,
    annotation_string_enum,
    enum_default,
)

# Typer vendors its own copy of click (`typer._click`), so a Typer app's objects
# are not instances of anything in the standalone `click` package and its
# parameter types are not click's singletons. Everything here is therefore
# matched structurally rather than by identity or isinstance — see #77.
_PARAM_TYPE_NAMES = {
    # click's own vocabulary
    "text": "str",
    "integer": "int",
    "float": "float",
    "boolean": "bool",
    # typer's vendored click reports Python names directly
    "str": "str",
    "int": "int",
    "bool": "bool",
    "string": "str",
}


def _click_type_to_str(param_type: Any) -> str:
    """Map a Click/Typer parameter type to a Python type name."""
    if type(param_type).__name__ in ("IntRange", "FloatRange"):
        return "int" if type(param_type).__name__ == "IntRange" else "float"
    name = getattr(param_type, "name", None)
    if isinstance(name, str) and name.lower() in _PARAM_TYPE_NAMES:
        return _PARAM_TYPE_NAMES[name.lower()]
    # Fall back to the class name: IntParamType -> "int".
    cls_name = type(param_type).__name__.removesuffix("ParamType").lower()
    return _PARAM_TYPE_NAMES.get(cls_name, "str")


def _child_commands(obj: Any) -> dict[str, Any] | None:
    """The sub-commands of a group, or None if this is a leaf command."""
    commands = getattr(obj, "commands", None)
    return commands if isinstance(commands, dict) else None


def _text_name(value: Any) -> str | None:
    """Return framework names without accepting placeholder objects."""
    return value if isinstance(value, str) and value else None


def _option_aliases(param: Any) -> list[str]:
    """Return Click/Typer option declarations in their public order."""
    if not hasattr(param, "secondary_opts"):
        return []
    primary = [
        option
        for option in getattr(param, "opts", ())
        if isinstance(option, str) and option.startswith("-")
    ]
    secondary = [
        option
        for option in param.secondary_opts
        if isinstance(option, str) and option.startswith("-")
    ]
    if primary and secondary:
        paired_count = min(len(primary), len(secondary))
        paired = [
            f"{primary[index]}/{secondary[index]}" for index in range(paired_count)
        ]
        unmatched_secondary = [f" /{option}" for option in secondary[paired_count:]]
        return [*paired, *primary[paired_count:], *unmatched_secondary]
    return [*primary, *secondary]


def _primary_option_name(aliases: list[str]) -> str | None:
    """Choose the long option spelling used by targets with one public alias."""
    primary = next((alias for alias in aliases if alias.startswith("--")), None)
    if primary is None and aliases:
        primary = aliases[0]
    return primary.split("/", 1)[0].lstrip("-") if primary else None


def _parameter_annotation_metadata(
    annotation: Any, signature_default: Any
) -> tuple[Any, Any]:
    """Read original option metadata in either inspector path."""
    metadata = None if isinstance(signature_default, Enum) else signature_default
    if get_origin(annotation) is Annotated:
        annotation, *extras = get_args(annotation)
        metadata = next(
            (
                extra
                for extra in extras
                if not isinstance(extra, Enum)
                and hasattr(extra, "help")
                and hasattr(extra, "default")
            ),
            metadata,
        )

    return annotation, metadata


def _plain_context_settings(settings: Any) -> Any:
    """Only builtin storage certifies lookup semantics; never invoke map hooks."""
    if settings is None:
        return None
    from typer.models import DefaultPlaceholder

    if type(settings) is DefaultPlaceholder:
        settings = settings.value
    return settings if settings is None or type(settings) is dict else _SENTINEL


def _automatic_envvar(context_settings: Any, inherited: bool = False) -> bool:
    """Track binding eligibility, never read or snapshot environment values."""
    context_settings = _plain_context_settings(context_settings)
    return (
        inherited
        or context_settings is _SENTINEL
        or (
            type(context_settings) is dict
            and context_settings.get("auto_envvar_prefix") is not None
        )
    )


def _unsupported_enum_context(settings: Any, inherited: bool = False) -> bool:
    """Token normalization inherits; resilient parsing is context-local."""
    settings = _plain_context_settings(settings)
    return (
        inherited
        or settings is _SENTINEL
        or (type(settings) is dict and settings.get("token_normalize_func") is not None)
    )


def _resilient_enum_context(settings: Any) -> bool:
    settings = _plain_context_settings(settings)
    return type(settings) is dict and (
        settings.get("resilient_parsing", False) is not False
        and settings.get("resilient_parsing") is not None
    )


def _context_default_map(context_settings: Any, inherited: Any = None) -> Any:
    """Explicit maps replace inherited maps; None retains the current lookup."""
    context_settings = _plain_context_settings(context_settings)
    if context_settings is _SENTINEL:
        return _SENTINEL
    configured = (
        context_settings.get("default_map") if type(context_settings) is dict else None
    )
    return inherited if configured is None else configured


def _child_default_map(default_map: Any, name: str) -> Any:
    return default_map.get(name) if type(default_map) is dict else default_map


def _has_context_default(default_map: Any, name: str) -> bool:
    # Do not invoke entries: Click permits callables here. Unknown map shapes
    # cannot certify an enum default either, but unrelated/None entries are inert.
    return default_map is not None and (
        type(default_map) is not dict or default_map.get(name) is not None
    )


def _registered_setting(app: Any, registration: Any, name: str) -> Any:
    """Read just one Typer setting with registration/callback/app precedence."""
    from typer.models import DefaultPlaceholder

    for owner in (
        registration,
        getattr(app, "registered_callback", None),
        getattr(app, "info", None),
    ):
        value = getattr(owner, name, _SENTINEL)
        if value is not _SENTINEL and not isinstance(value, DefaultPlaceholder):
            return value
    return None


def _guard_enum_parameter_metadata(
    metadata: Any,
    *,
    automatic_envvar: bool = False,
    context_default: bool = False,
    unsupported_context: bool = False,
) -> None:
    # Plain enum defaults can expose members named like option settings.
    if isinstance(metadata, Enum):
        metadata = None
    if getattr(metadata, "default_factory", None) is not None:
        raise TypeError("String-enum default factories are not supported")
    if getattr(metadata, "envvar", None) is not None or automatic_envvar:
        raise TypeError("Environment-backed enum parameters are not supported")
    if any(
        getattr(metadata, name, None) is not None for name in ("click_type", "parser")
    ):
        raise TypeError("Custom enum parameter types and parsers are not supported")
    if not getattr(metadata, "case_sensitive", True):
        raise TypeError("Unsupported case-insensitive enum parameters")
    prompt = getattr(metadata, "prompt", False)
    if prompt is not None and prompt is not False:
        raise TypeError("Prompt-backed enum parameters are not supported")
    if unsupported_context:
        raise TypeError("Custom enum context settings are not supported")
    if context_default:
        raise TypeError("Context-backed enum defaults are not supported")


def _enum_parameter_default(spec: StringEnumSpec, default: Any) -> Any:
    if spec.many and default is None:
        # Use only Typer's builtin converter on an empty tuple, never a source
        # callback, enum parser or default factory. Legacy Typer yields []; newer
        # versions preserve None. Read the installed API instead of version tags.
        import typer.main

        factory: Any = getattr(typer.main, "generate_list_convertor", None)
        if callable(factory):
            converter: Any
            if "default_value" in inspect.signature(factory).parameters:
                converter = factory(None, default_value=None)
            else:
                converter = factory(None)
            default = converter(())
        else:
            normalize: Any = getattr(typer.main, "_normalize_collection_value", None)
            if not callable(normalize):
                raise TypeError("Unsupported native enum collection normalization")
            # Typer 0.29 moved omission normalization to the command callback.
            # Supply only builtin metadata and an empty tuple, never a source
            # parameter, factory, parser, callback, or annotation provider.
            metadata = types.SimpleNamespace(default=None, multiple=True, nargs=1)
            default = normalize(metadata, ())
        if default is not None and (type(default) is not list or default):
            raise TypeError("Unsupported native enum collection default")
    return enum_default(spec, default)


def _registered_parameter_details(
    annotation: Any,
    signature_default: Any,
    *,
    automatic_envvar: bool = False,
    context_default: bool = False,
    unsupported_context: bool = False,
) -> tuple[Any, Any, str, str | None, list[str], bool, dict[str, Any]]:
    """Normalize callback annotations and Typer metadata without building Click."""
    annotation, metadata = _parameter_annotation_metadata(annotation, signature_default)
    enum = annotation_string_enum(annotation)
    if enum is not None:
        # Arguments do not participate in automatic option environment lookup.
        option = hasattr(metadata, "prompt") or (
            not hasattr(metadata, "param_decls")
            and signature_default is not inspect.Parameter.empty
            and signature_default is not Ellipsis
        )
        _guard_enum_parameter_metadata(
            metadata,
            automatic_envvar=automatic_envvar and option,
            context_default=context_default,
            unsupported_context=unsupported_context,
        )
    default_source = (
        metadata if signature_default is inspect.Parameter.empty else signature_default
    )
    raw_default = (
        default_source
        if isinstance(default_source, Enum)
        else getattr(default_source, "default", default_source)
    )
    declared_aliases = [
        declaration
        for declaration in (getattr(metadata, "param_decls", None) or ())
        if isinstance(declaration, str) and declaration.startswith("-")
    ]
    metadata_default = getattr(metadata, "default", inspect.Parameter.empty)
    if isinstance(metadata_default, str) and metadata_default.startswith("-"):
        declared_aliases.insert(0, metadata_default)
        if signature_default is inspect.Parameter.empty:
            raw_default = inspect.Parameter.empty
    default = (
        _SENTINEL
        if raw_default is inspect.Parameter.empty or raw_default is Ellipsis
        else raw_default
    )
    if (
        enum is not None
        and enum.many
        and (
            default is _SENTINEL
            or (hasattr(metadata, "param_decls") and not hasattr(metadata, "prompt"))
        )
    ):
        raise TypeError("Only optional repeatable enum options are supported")
    help_text = getattr(metadata, "help", "")
    description = help_text if isinstance(help_text, str) else ""
    numeric_range = (
        {"unsupported_numeric_range": True}
        if getattr(metadata, "click_type", None) is not None
        else cli_numeric_range(metadata, constructed=False)
    )
    numeric_range, default = cli_range_default(
        numeric_range, python_type_name(annotation), default
    )
    if enum is None:
        option = hasattr(metadata, "prompt") or (
            not hasattr(metadata, "param_decls")
            and signature_default is not inspect.Parameter.empty
            and signature_default is not Ellipsis
        )
        collection = cli_string_list(
            annotation,
            metadata,
            default,
            option=option,
            automatic_envvar=automatic_envvar and option,
            context_default=context_default,
            unsupported_context=unsupported_context,
        )
        if collection is not None:
            type_name, default, minimum_items = collection
            annotation = (
                (list[str] | None) if type_name.startswith("Optional[") else list[str]
            )
            numeric_range = dict(numeric_range, minimum_items=minimum_items)
    return (
        annotation,
        default,
        description,
        _primary_option_name(declared_aliases),
        declared_aliases,
        callable(getattr(metadata, "callback", None)),
        numeric_range,
    )


def _callback_provider(candidate: Any) -> bool:
    """Do not ask a parameter callback for its signature or annotations."""
    if type(candidate) is types.FunctionType:
        namespace = vars(candidate)
        return (
            getattr(candidate, "__annotate__", None) is not None
            or "__wrapped__" in namespace
            or "__signature__" in namespace
        )
    # Callable instances/partials may hide an annotated implementation. The
    # registered inspector can retain their refusal without native introspection.
    return callable(candidate)


def _parameter_callback_provider(metadata: Any, seen: set[int] | None = None) -> bool:
    from typer.models import ArgumentInfo, OptionInfo

    # A loaded whole Annotated alias can hide parameter metadata behind one name.
    # Inspect only the known typing implementation's stored metadata, not a
    # callback's annotations or arbitrary objects' attribute hooks.
    if type(metadata) is type(Annotated[bool, None]):
        if seen is None:
            seen = set()
        if id(metadata) in seen or len(seen) >= 64:
            return True
        seen.add(id(metadata))
        extras = vars(metadata).get("__metadata__")
        if type(extras) is not tuple:
            return True
        return any(_parameter_callback_provider(extra, seen) for extra in extras)
    if type(metadata) is OptionInfo or type(metadata) is ArgumentInfo:
        return _callback_provider(vars(metadata).get("callback"))
    # Opaque parameter-info subclasses must not reach native introspection.
    # Use identity, not custom metaclass equality or metadata attribute hooks.
    return any(
        base is OptionInfo or base is ArgumentInfo
        for base in type.__getattribute__(type(metadata), "__mro__")
    )


def _annotation_callback_provider(node: ast.AST, namespace: dict[str, Any]) -> bool:
    """Read loaded metadata aliases and callback= references without evaluation."""
    for item in ast.walk(node):
        callback_reference = isinstance(item, ast.keyword) and item.arg == "callback"
        if callback_reference:
            expression = item.value
        elif isinstance(item, (ast.Name, ast.Attribute)):
            expression = item
        else:
            continue
        attributes: list[str] = []
        while isinstance(expression, ast.Attribute):
            attributes.append(expression.attr)
            expression = expression.value
        if isinstance(expression, ast.Constant) and expression.value is None:
            continue
        if not isinstance(expression, ast.Name) or expression.id not in namespace:
            if callback_reference:
                return True
            continue
        candidate = namespace[expression.id]
        for attribute in reversed(attributes):
            if type(candidate) is not types.ModuleType or attribute not in vars(
                candidate
            ):
                # Class/custom descriptors are opaque; do not probe their hooks.
                return True
            candidate = vars(candidate)[attribute]
        if (
            _callback_provider(candidate)
            if callback_reference
            else _parameter_callback_provider(candidate)
        ):
            return True
    return False


def _command_callback_provider(callback: types.FunctionType) -> bool:
    """Preflight metadata before Typer builds wrappers for parameter callbacks."""
    if "__wrapped__" in vars(callback) or "__signature__" in vars(callback):
        # The effective command signature can contain callback metadata absent
        # from this function's own defaults/annotations. Do not build native
        # parameter-callback wrappers to discover it.
        return True

    defaults = (
        *(callback.__defaults__ or ()),
        *(callback.__kwdefaults__ or {}).values(),
    )
    for metadata in defaults:
        if _parameter_callback_provider(metadata):
            return True
    if getattr(callback, "__annotate__", None) is None:
        for annotation in callback.__annotations__.values():
            if type(annotation) is str:
                try:
                    node = ast.parse(annotation, mode="eval")
                except SyntaxError:
                    continue
                if _annotation_callback_provider(node, callback.__globals__):
                    return True
            elif get_origin(annotation) is Annotated:
                for metadata in get_args(annotation)[1:]:
                    if _parameter_callback_provider(metadata):
                        return True
        return False
    # Do not evaluate a deferred command annotation merely to discover its
    # callback= metadata. Read only matching file-backed annotation syntax.
    metadata = callable_source_metadata(callback)
    location = metadata["source_location"]
    if location is None:
        return True
    try:
        with tokenize.open(location[0]) as stream:
            source = stream.read()
        if (
            hashlib.sha256(source.encode("utf-8")).hexdigest()
            != metadata["source_digest"]
        ):
            return True
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.lineno == location[1]
        )
        for parameter in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            annotation = parameter.annotation
            if isinstance(annotation, ast.Constant) and type(annotation.value) is str:
                annotation = ast.parse(annotation.value, mode="eval")
            if annotation is not None and _annotation_callback_provider(
                annotation, callback.__globals__
            ):
                return True
        return False
    except (OSError, ValueError, SyntaxError, UnicodeError, StopIteration):
        return True


def _registered_callback_provider(app: Any, seen: set[int] | None = None) -> bool:
    """Avoid native construction before it inspects an unsupported callback."""
    if seen is None:
        seen = set()
    if id(app) in seen:
        return False
    seen.add(id(app))
    registrations = [
        *(getattr(app, "registered_commands", ()) or ()),
        getattr(app, "registered_callback", None),
        getattr(app, "info", None),
    ]
    for command in registrations:
        callback = getattr(command, "callback", None)
        if callable(callback) and (
            type(callback) is not types.FunctionType
            or _command_callback_provider(callback)
        ):
            return True
    return any(
        _registered_callback_provider(group.typer_instance, seen)
        for group in (getattr(app, "registered_groups", ()) or ())
    )


class CLIInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []
        if _registered_callback_provider(app):
            self._extract_registered_app(app, tools)
            return tools

        # Get the underlying Click group
        click_group = None
        try:
            # Typer creates a Click group via its __call__ or internal method
            click_group = app  # Try using it directly first
            if hasattr(app, "_get_command"):
                click_group = app._get_command()
            elif hasattr(app, "registered_commands"):
                # Build the click group by invoking typer internals
                import typer.main

                click_group = typer.main.get_command(app)
        except Exception:
            registered = getattr(app, "registered_commands", None)
            if isinstance(registered, list):
                self._extract_registered_app(app, tools)
                return tools

        if click_group is None:
            return tools

        # Typer 0.29's Click-compatible parameters expose the original Typer
        # TypeDescriptor instead of Click's ``type``. This is a known structural
        # API change; use the registration reader, which interprets original
        # annotations/OptionInfo without running factories or callbacks.
        if self._uses_typer_type_descriptors(click_group):
            self._extract_registered_app(
                self._descriptor_registration_view(click_group), tools
            )
            return tools

        self._extract_commands(click_group, tools, prefix="")
        return tools

    @staticmethod
    def _uses_typer_type_descriptors(command: Any) -> bool:
        """Recognize the Typer 0.29 parameter representation structurally."""
        commands = _child_commands(command)
        children = commands.values() if commands is not None else (command,)
        for child in children:
            nested = _child_commands(child)
            if nested is not None:
                if CLIInspector._uses_typer_type_descriptors(child):
                    return True
                continue
            params = getattr(child, "params", ())
            if any(
                not hasattr(param, "type")
                and type(getattr(param, "type_descriptor", None)).__name__
                == "TypeDescriptor"
                for param in params
            ):
                return True
        return False

    @staticmethod
    def _descriptor_registration_view(command: Any) -> Any:
        """Reuse original callbacks when callers supply an already-built tree."""
        children = _child_commands(command)
        view = types.SimpleNamespace(
            info=command,
            registered_callback=command if children is not None else None,
            registered_commands=[],
            registered_groups=[],
        )
        for child in children.values() if children is not None else (command,):
            if _child_commands(child) is not None:
                view.registered_groups.append(
                    types.SimpleNamespace(
                        typer_instance=CLIInspector._descriptor_registration_view(
                            child
                        ),
                        name=getattr(child, "name", None),
                        context_settings=getattr(child, "context_settings", None),
                    )
                )
            else:
                callback = getattr(child, "callback", None)
                if callable(callback):
                    view.registered_commands.append(
                        types.SimpleNamespace(
                            callback=inspect.unwrap(callback),
                            native_parameters=getattr(child, "params", ()),
                            name=getattr(child, "name", None),
                            help=getattr(child, "help", None),
                            context_settings=getattr(child, "context_settings", None),
                        )
                    )
        return view

    def _extract_registered_app(
        self,
        app: Any,
        tools: list[ToolInfo],
        prefix: str = "",
        seen: set[int] | None = None,
        automatic_envvar: bool = False,
        registration: Any = None,
        default_map: Any = None,
        unsupported_context: bool = False,
    ) -> None:
        """Inspect Typer callbacks when its Click tree cannot be constructed."""
        if seen is None:
            seen = set()
        app_id = id(app)
        if app_id in seen:
            return
        seen.add(app_id)

        commands = getattr(app, "registered_commands", None)
        if not isinstance(commands, list):
            return

        is_group = bool(
            registration is not None
            or getattr(app, "registered_callback", None)
            or getattr(getattr(app, "info", None), "callback", None)
            or getattr(app, "registered_groups", None)
            or len(commands) > 1
        )
        # Unnamed add_typer groups are flattened: their context is unused.
        if is_group and (
            registration is None
            or _text_name(_registered_setting(app, registration, "name"))
        ):
            settings = _registered_setting(app, registration, "context_settings")
            automatic_envvar = _automatic_envvar(settings, automatic_envvar)
            default_map = _context_default_map(settings, default_map)
            unsupported_context = _unsupported_enum_context(
                settings, unsupported_context
            )

        for command in commands:
            callback = getattr(command, "callback", None)
            if not callable(callback):
                continue

            declared_name = _text_name(getattr(command, "name", None))
            command_name = declared_name or callback.__name__.replace("_", "-")
            interface_name = f"{prefix}{command_name}"
            name = interface_name.replace("-", "_")
            description = (
                getattr(command, "help", None) or inspect.getdoc(callback) or ""
            )
            signature = inspect.signature(callback)
            try:
                annotations = inspect.get_annotations(callback, eval_str=True)
            except Exception:
                annotations = inspect.get_annotations(callback, eval_str=False)

            context_settings = getattr(command, "context_settings", None)
            if not is_group and not context_settings:
                context_settings = getattr(
                    getattr(app, "info", None), "context_settings", None
                )
            command_auto_envvar = _automatic_envvar(context_settings, automatic_envvar)
            command_unsupported_context = _unsupported_enum_context(
                context_settings, unsupported_context
            ) or _resilient_enum_context(context_settings)
            command_default_map = _context_default_map(
                context_settings,
                _child_default_map(default_map, command_name)
                if is_group
                else default_map,
            )
            parameters: list[ParameterInfo] = []
            native_parameters = {
                item.name: item
                for item in getattr(command, "native_parameters", ())
                if isinstance(getattr(item, "name", None), str)
            }
            for param in signature.parameters.values():
                (
                    annotation,
                    default,
                    parameter_description,
                    parameter_interface_name,
                    aliases,
                    unsupported_callback,
                    numeric_range,
                ) = _registered_parameter_details(
                    annotations.get(param.name, param.annotation),
                    param.default,
                    automatic_envvar=command_auto_envvar,
                    unsupported_context=command_unsupported_context,
                    context_default=_has_context_default(
                        command_default_map, param.name
                    ),
                )
                native_parameter = native_parameters.get(param.name)
                if native_parameter is not None:
                    aliases = _option_aliases(native_parameter)
                    parameter_interface_name = _primary_option_name(aliases)
                _, original_metadata = _parameter_annotation_metadata(
                    annotations.get(param.name, param.annotation), param.default
                )
                informational_callback = capture_parameter_informational_callback(
                    annotation,
                    original_metadata,
                    default,
                    automatic_envvar=command_auto_envvar,
                    context_default=_has_context_default(
                        command_default_map, param.name
                    ),
                    unsupported_context=command_unsupported_context,
                )
                enum = annotation_string_enum(annotation)
                if enum is not None and default is not _SENTINEL:
                    default = _enum_parameter_default(enum, default)
                parameters.append(
                    ParameterInfo(
                        name=param.name,
                        type_annotation=python_type_name(annotation),
                        default=default,
                        description=parameter_description,
                        interface_name=parameter_interface_name,
                        aliases=aliases,
                        unsupported_callback=unsupported_callback,
                        informational_callback=informational_callback,
                        string_enum=enum,
                        **numeric_range,
                    )
                )

            tools.append(
                ToolInfo(
                    name=name,
                    interface_name=interface_name,
                    description=description,
                    parameters=parameters,
                    return_type="str",
                    function_body=extract_function_body(callback),
                    is_async=inspect.iscoroutinefunction(callback),
                    source_imports=extract_source_imports(callback),
                    **inspected_callable_metadata(callback),
                )
            )

        groups = getattr(app, "registered_groups", None)
        if not isinstance(groups, list):
            return
        for group in groups:
            nested = getattr(group, "typer_instance", None)
            if nested is None:
                continue
            group_name = _text_name(getattr(group, "name", None))
            if group_name is None:
                group_name = _text_name(
                    getattr(getattr(nested, "info", None), "name", None)
                )
            nested_prefix = f"{prefix}{group_name}_" if group_name else prefix
            self._extract_registered_app(
                # Mounts have independent contexts; only ancestor cycles repeat.
                nested,
                tools,
                nested_prefix,
                seen.copy(),
                automatic_envvar,
                group,
                _child_default_map(default_map, group_name)
                if group_name
                else default_map,
                unsupported_context,
            )

    def _extract_commands(
        self,
        group: Any,
        tools: list[ToolInfo],
        prefix: str = "",
        automatic_envvar: bool = False,
        default_map: Any = None,
        unsupported_context: bool = False,
    ) -> None:
        """Recursively extract commands from Click/Typer groups."""
        unsupported_context = _unsupported_enum_context(
            getattr(group, "context_settings", None), unsupported_context
        )
        automatic_envvar = _automatic_envvar(
            getattr(group, "context_settings", None), automatic_envvar
        )
        default_map = _context_default_map(
            getattr(group, "context_settings", None), default_map
        )
        commands = _child_commands(group)
        is_group = commands is not None
        if commands is None:
            # A single command rather than a group.
            commands = {getattr(group, "name", None) or "main": group}

        for cmd_name, cmd in commands.items():
            if cmd_name is None:
                continue

            interface_name = f"{prefix}{cmd_name}"
            full_name = interface_name.replace("-", "_")

            # Recurse into sub-groups
            if _child_commands(cmd) is not None:
                self._extract_commands(
                    cmd,
                    tools,
                    prefix=f"{full_name}_",
                    automatic_envvar=automatic_envvar,
                    default_map=_child_default_map(default_map, cmd_name),
                    unsupported_context=unsupported_context,
                )
                continue

            self._extract_single_command(
                cmd,
                full_name,
                interface_name,
                tools,
                automatic_envvar,
                _child_default_map(default_map, cmd_name) if is_group else default_map,
                unsupported_context,
            )

    def _extract_single_command(
        self,
        cmd: Any,
        name: str,
        interface_name: str,
        tools: list[ToolInfo],
        automatic_envvar: bool = False,
        default_map: Any = None,
        unsupported_context: bool = False,
    ) -> None:
        """Extract a single Click command into a ToolInfo."""
        unsupported_context = _unsupported_enum_context(
            getattr(cmd, "context_settings", None), unsupported_context
        ) or _resilient_enum_context(getattr(cmd, "context_settings", None))
        default_map = _context_default_map(
            getattr(cmd, "context_settings", None), default_map
        )
        automatic_envvar = _automatic_envvar(
            getattr(cmd, "context_settings", None), automatic_envvar
        )
        description = cmd.help or ""
        callback = getattr(cmd, "callback", None)
        callback_params: dict[str, inspect.Parameter] = {}
        if callback is not None:
            try:
                callback_params = dict(
                    inspect.signature(
                        inspect.unwrap(callback), eval_str=True
                    ).parameters
                )
            except (TypeError, ValueError):
                pass

        params: list[ParameterInfo] = []
        for param in cmd.params:
            if param.name is None or (
                not getattr(param, "expose_value", True)
                and param.name not in callback_params
            ):
                # Framework help/completion options are not callback inputs.
                # Retain user parameters (even named help) and their guards.
                continue

            type_str = _click_type_to_str(param.type)

            # Check if parameter is required via Click's own flag
            default = _SENTINEL
            if not getattr(param, "required", False):
                default = param.default

            numeric_range, default = cli_range_default(
                cli_numeric_range(param.type, constructed=True), type_str, default
            )
            desc = ""
            if hasattr(param, "help") and param.help:
                desc = param.help
            else:
                original = callback_params.get(param.name)
                metadata = (
                    _parameter_annotation_metadata(
                        original.annotation, original.default
                    )[1]
                    if original
                    else None
                )
                original_help = getattr(metadata, "help", None)
                if isinstance(original_help, str):
                    desc = original_help

            original = callback_params.get(param.name)
            enum = annotation_string_enum(original.annotation) if original else None
            minimum_items = None
            if enum is None and original is not None:
                list_annotation, list_metadata = _parameter_annotation_metadata(
                    original.annotation, original.default
                )
                option = getattr(param, "param_type_name", None) == "option"
                collection = cli_string_list(
                    list_annotation,
                    list_metadata,
                    default,
                    option=option,
                    automatic_envvar=automatic_envvar
                    and option
                    and getattr(param, "allow_from_autoenv", True),
                    context_default=_has_context_default(default_map, param.name),
                    unsupported_context=unsupported_context,
                    native_parameter=param,
                )
                if collection is not None:
                    type_str, default, minimum_items = collection
            if enum is not None:
                assert original is not None
                _, metadata = _parameter_annotation_metadata(
                    original.annotation, original.default
                )
                _guard_enum_parameter_metadata(
                    metadata,
                    automatic_envvar=(
                        automatic_envvar
                        and getattr(param, "param_type_name", None) == "option"
                        and getattr(param, "allow_from_autoenv", True)
                    ),
                    context_default=_has_context_default(default_map, param.name),
                    unsupported_context=unsupported_context,
                )
                if (
                    not getattr(param.type, "case_sensitive", True)
                    or bool(getattr(param, "multiple", False)) != enum.many
                    or getattr(param, "nargs", 1) != 1
                    or (
                        enum.many
                        and (
                            default is _SENTINEL or not hasattr(param, "secondary_opts")
                        )
                    )
                ):
                    raise TypeError(
                        "Collection or case-insensitive enum parameters are not supported"
                    )
                if default is not _SENTINEL:
                    default = _enum_parameter_default(enum, default)
            informational_callback = None
            if original is not None:
                original_annotation, original_metadata = _parameter_annotation_metadata(
                    original.annotation, original.default
                )
                informational_callback = capture_parameter_informational_callback(
                    original_annotation,
                    original_metadata,
                    default,
                    automatic_envvar=(
                        automatic_envvar and getattr(param, "allow_from_autoenv", True)
                    ),
                    context_default=_has_context_default(default_map, param.name),
                    unsupported_context=unsupported_context,
                )
            aliases = _option_aliases(param)
            params.append(
                ParameterInfo(
                    name=param.name,
                    type_annotation=type_str,
                    default=default,
                    description=desc,
                    interface_name=_primary_option_name(aliases),
                    aliases=aliases,
                    unsupported_callback=callable(getattr(param, "callback", None)),
                    informational_callback=informational_callback,
                    string_enum=enum,
                    minimum_items=minimum_items,
                    **numeric_range,
                )
            )

        # Extract function body and async status from the callback
        fn_body = extract_function_body(callback) if callback else None
        src_imports = extract_source_imports(callback) if callback else []
        is_async = asyncio.iscoroutinefunction(callback) if callback else False

        tools.append(
            ToolInfo(
                name=name,
                interface_name=interface_name,
                description=description,
                parameters=params,
                return_type="str",
                function_body=fn_body,
                is_async=is_async,
                source_imports=src_imports,
                **inspected_callable_metadata(callback) if callback else {},
            )
        )
