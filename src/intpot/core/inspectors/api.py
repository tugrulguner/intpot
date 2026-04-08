"""Extract endpoints from a FastAPI app instance."""

from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

from intpot.core.inspectors._utils import (
    extract_function_body,
    extract_source_imports,
    python_type_name,
)
from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ParameterSource, ToolInfo

_INTERNAL_ROUTES = {
    "openapi",
    "swagger_ui_html",
    "swagger_ui_redirect",
    "redoc_html",
    "root",
}

_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")


def _is_pydantic_undefined(obj: Any) -> bool:
    """Check if an object is PydanticUndefined (used by Body(...) etc.)."""
    return type(obj).__name__ == "PydanticUndefinedType"


def _is_depends(obj: Any) -> bool:
    """Check if an object is a FastAPI Depends() instance."""
    cls_name = type(obj).__name__
    module = type(obj).__module__ or ""
    return cls_name == "Depends" and "fastapi" in module


_FASTAPI_SOURCE_MAP: dict[str, ParameterSource] = {
    "Query": ParameterSource.QUERY,
    "Header": ParameterSource.HEADER,
    "Body": ParameterSource.BODY,
    "Path": ParameterSource.PATH,
    "Form": ParameterSource.BODY,  # treat Form as body
    "File": ParameterSource.BODY,
}


def _param_source(default: Any, param_name: str, path_params: set[str]) -> ParameterSource:
    if param_name in path_params:
        return ParameterSource.PATH
    if default is not inspect.Parameter.empty and hasattr(default, "__class__"):
        cls_name = type(default).__name__
        module = getattr(type(default), "__module__", "") or ""
        if "fastapi" in module and cls_name in _FASTAPI_SOURCE_MAP:
            return _FASTAPI_SOURCE_MAP[cls_name]
    return ParameterSource.BODY


class APIInspector(BaseInspector):
    def inspect(self, app: Any) -> list[ToolInfo]:
        tools: list[ToolInfo] = []

        for route in app.routes:
            if not hasattr(route, "endpoint"):
                continue

            endpoint = route.endpoint
            name = endpoint.__name__

            # Skip FastAPI's built-in routes
            if name in _INTERNAL_ROUTES:
                continue

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
            dependencies: list[str] = []
            for param_name, param in sig.parameters.items():
                # Skip Depends() parameters — record as dependencies
                if param.default is not inspect.Parameter.empty and _is_depends(
                    param.default
                ):
                    dep_fn = getattr(param.default, "dependency", None)
                    dep_name = getattr(dep_fn, "__name__", None) or param_name
                    dependencies.append(dep_name)
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

                params.append(
                    ParameterInfo(
                        name=param_name,
                        type_annotation=type_str,
                        default=default,
                        description=desc,
                        source=_param_source(param.default, param_name, path_params),
                    )
                )

            return_annotation = type_hints.get("return", sig.return_annotation)
            return_type = python_type_name(return_annotation)

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
