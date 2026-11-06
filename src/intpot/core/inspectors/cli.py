"""Extract commands from a Typer app instance."""

from __future__ import annotations

import asyncio
import inspect
from enum import Enum
from typing import Annotated, Any, get_args, get_origin

from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_type_name,
)
from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo
from intpot.core.numeric_ranges import cli_numeric_range, cli_range_default
from intpot.core.provenance import inspected_callable_metadata
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


def _automatic_envvar(context_settings: Any, inherited: bool = False) -> bool:
    """Track binding eligibility, never read or snapshot environment values."""
    return inherited or (
        isinstance(context_settings, dict)
        and context_settings.get("auto_envvar_prefix") is not None
    )


def _context_default_map(context_settings: Any, inherited: Any = None) -> Any:
    """Explicit maps replace inherited maps; None retains the current lookup."""
    configured = (
        dict.get(context_settings, "default_map")
        if isinstance(context_settings, dict)
        else None
    )
    return inherited if configured is None else configured


def _child_default_map(default_map: Any, name: str) -> Any:
    return dict.get(default_map, name) if isinstance(default_map, dict) else default_map


def _has_context_default(default_map: Any, name: str) -> bool:
    # Do not invoke entries: Click permits callables here. Unknown map shapes
    # cannot certify an enum default either, but unrelated/None entries are inert.
    return default_map is not None and (
        not isinstance(default_map, dict) or dict.get(default_map, name) is not None
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
    metadata: Any, *, automatic_envvar: bool = False, context_default: bool = False
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
    if context_default:
        raise TypeError("Context-backed enum defaults are not supported")


def _enum_parameter_default(spec: StringEnumSpec, default: Any) -> Any:
    if spec.many and default is None:
        # Use only Typer's builtin converter on an empty tuple, never a source
        # callback, enum parser or default factory. Legacy Typer yields []; newer
        # versions preserve None. Read the installed API instead of version tags.
        import typer.main

        factory: Any = typer.main.generate_list_convertor
        if "default_value" in inspect.signature(factory).parameters:
            converter = factory(None, default_value=None)
        else:
            converter = factory(None)
        default = converter(())
        if default is not None and (type(default) is not list or default):
            raise TypeError("Unsupported native enum collection default")
    return enum_default(spec, default)


def _registered_parameter_details(
    annotation: Any,
    signature_default: Any,
    *,
    automatic_envvar: bool = False,
    context_default: bool = False,
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
    return (
        annotation,
        default,
        description,
        _primary_option_name(declared_aliases),
        declared_aliases,
        callable(getattr(metadata, "callback", None)),
        numeric_range,
    )


class CLIInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []

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

        self._extract_commands(click_group, tools, prefix="")
        return tools

    def _extract_registered_app(
        self,
        app: Any,
        tools: list[ToolInfo],
        prefix: str = "",
        seen: set[int] | None = None,
        automatic_envvar: bool = False,
        registration: Any = None,
        default_map: Any = None,
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
            command_default_map = _context_default_map(
                context_settings,
                _child_default_map(default_map, command_name)
                if is_group
                else default_map,
            )
            parameters: list[ParameterInfo] = []
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
                    context_default=_has_context_default(
                        command_default_map, param.name
                    ),
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
            )

    def _extract_commands(
        self,
        group: Any,
        tools: list[ToolInfo],
        prefix: str = "",
        automatic_envvar: bool = False,
        default_map: Any = None,
    ) -> None:
        """Recursively extract commands from Click/Typer groups."""
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
                )
                continue

            self._extract_single_command(
                cmd,
                full_name,
                interface_name,
                tools,
                automatic_envvar,
                _child_default_map(default_map, cmd_name) if is_group else default_map,
            )

    def _extract_single_command(
        self,
        cmd: Any,
        name: str,
        interface_name: str,
        tools: list[ToolInfo],
        automatic_envvar: bool = False,
        default_map: Any = None,
    ) -> None:
        """Extract a single Click command into a ToolInfo."""
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
                    string_enum=enum,
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
