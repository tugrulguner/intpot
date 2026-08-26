"""Extract endpoints from a FastAPI app instance."""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Iterable, Iterator
from typing import Any, cast

from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_return_type_name,
    python_type_name,
)
from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ParamSource, ToolInfo

_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")


def _is_pydantic_undefined(obj: Any) -> bool:
    """Check if an object is PydanticUndefined (used by Body(...) etc.)."""
    return type(obj).__name__ == "PydanticUndefinedType"


def _get_param_source(obj: Any) -> ParamSource | None:
    """Detect if a default is Query(), Header(), Body(), or Path()."""
    cls_name = type(obj).__name__
    module = getattr(type(obj), "__module__", "") or ""

    if "fastapi" not in module:
        return None

    mapping = {
        "Query": ParamSource.query,
        "Header": ParamSource.header,
        "Body": ParamSource.body,
        "Path": ParamSource.path,
    }
    return mapping.get(cls_name)


def _is_normalized_api_route(route: Any) -> bool:
    """Recognize the FastAPI route shape consumed by this inspector."""
    return all(hasattr(route, attr) for attr in ("endpoint", "dependant", "methods"))


def _iter_api_routes(app: Any) -> Iterator[Any]:
    """Yield normalized FastAPI routes, including lazily included routers."""
    seen: set[int] = set()

    def visit(route: Any) -> Iterator[Any]:
        identity = id(route)
        if identity in seen:
            return
        seen.add(identity)

        if _is_normalized_api_route(route):
            yield route
            return

        effective_candidates: Any = getattr(route, "effective_candidates", None)
        if not callable(effective_candidates):
            return
        for candidate in cast(Iterable[Any], effective_candidates()):
            yield from visit(candidate)

    for route in app.routes:
        yield from visit(route)


def _dependency_names(route: Any) -> list[str]:
    """Collect FastAPI's normalized dependency graph in traversal order."""
    names: list[str] = []
    seen: set[int] = set()

    def visit(dependant: Any) -> None:
        for dependency in getattr(dependant, "dependencies", ()):
            identity = id(dependency)
            if identity in seen:
                continue
            seen.add(identity)
            call = getattr(dependency, "call", None)
            name = (
                getattr(call, "__name__", None)
                or getattr(type(call), "__name__", None)
                or repr(call)
            )
            names.append(name)
            visit(dependency)

    visit(route.dependant)
    return names


class APIInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []

        for route in _iter_api_routes(app):
            # Only the user's own endpoints are APIRoute. FastAPI registers its
            # docs endpoints (/openapi.json, /docs, /redoc) as plain Starlette
            # Routes, so this excludes them exactly. Filtering by function name
            # instead used to drop any endpoint the user happened to call
            # `root` — i.e. the usual handler for `/`.
            endpoint = route.endpoint
            name = endpoint.__name__

            description = endpoint.__doc__ or ""
            description = description.strip()

            # Capture HTTP methods from the route
            methods = getattr(route, "methods", None) or {"POST"}
            http_method = next(iter(sorted(methods))).upper()

            # Capture route path
            route_path = getattr(route, "path", None)

            # Extract path parameter names
            path_params = set()
            if route_path:
                path_params = set(_PATH_PARAM_RE.findall(route_path))

            sig = inspect.signature(endpoint)
            type_hints: dict[str, Any] = {}
            try:
                type_hints = inspect.get_annotations(endpoint, eval_str=True)
            except Exception:
                pass

            params: list[ParameterInfo] = []
            dependencies = _dependency_names(route)
            dependency_params = {
                dependency.name
                for dependency in route.dependant.dependencies
                if dependency.name is not None
            }
            for param_name, param in sig.parameters.items():
                # FastAPI's dependant graph normalizes default Depends,
                # Annotated Depends, Security, and nested dependencies.
                if param_name in dependency_params:
                    continue

                annotation = type_hints.get(param_name, param.annotation)
                type_str = python_type_name(annotation)

                default = _SENTINEL
                if param.default is not inspect.Parameter.empty:
                    # FastAPI uses special default objects (Query, Path, Body, etc.)
                    raw_default = param.default
                    if hasattr(raw_default, "default"):
                        # It's a FastAPI FieldInfo — preserve None as a valid default
                        inner = raw_default.default
                        default = _SENTINEL if _is_pydantic_undefined(inner) else inner
                    else:
                        default = raw_default

                desc = ""
                if (
                    param.default is not inspect.Parameter.empty
                    and hasattr(param.default, "description")
                    and param.default.description
                ):
                    desc = param.default.description

                # Mark path parameters in description
                if param_name in path_params and not desc:
                    desc = f"Path parameter from {route_path}"

                param_source = None
                if param.default is not inspect.Parameter.empty:
                    param_source = _get_param_source(param.default)

                # Fall back to the path if name is in path params and no FastAPI annotation
                if param_source is None and param_name in path_params:
                    param_source = ParamSource.path

                params.append(
                    ParameterInfo(
                        name=param_name,
                        type_annotation=type_str,
                        default=default,
                        description=desc,
                        param_source=param_source,
                    )
                )

            return_annotation = type_hints.get("return", sig.return_annotation)
            return_type = python_return_type_name(return_annotation)

            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    parameters=params,
                    return_type=return_type,
                    http_method=http_method,
                    function_body=extract_function_body(endpoint),
                    source_imports=extract_source_imports(endpoint),
                    is_async=asyncio.iscoroutinefunction(endpoint),
                    route_path=route_path,
                    dependencies=dependencies,
                )
            )

        return tools
