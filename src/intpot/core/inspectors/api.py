"""Extract endpoints from a FastAPI app instance."""

from __future__ import annotations

import inspect
from typing import Any

from intpot.core.inspectors.base import BaseInspector
from intpot.core.models import _SENTINEL, ParameterInfo, ToolInfo


def _python_type_name(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty or annotation is None:
        return "str"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


_INTERNAL_ROUTES = {
    "openapi",
    "swagger_ui_html",
    "swagger_ui_redirect",
    "redoc_html",
    "root",
}


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

            sig = inspect.signature(endpoint)
            type_hints = {}
            try:
                type_hints = inspect.get_annotations(endpoint, eval_str=True)
            except Exception:
                pass

            params: list[ParameterInfo] = []
            for param_name, param in sig.parameters.items():
                annotation = type_hints.get(param_name, param.annotation)
                type_str = _python_type_name(annotation)

                default = _SENTINEL
                if param.default is not inspect.Parameter.empty:
                    # FastAPI uses special default objects (Query, Path, Body, etc.)
                    raw_default = param.default
                    if hasattr(raw_default, "default"):
                        # It's a FastAPI FieldInfo
                        if raw_default.default is not None:
                            default = raw_default.default
                    else:
                        default = raw_default

                desc = ""
                if hasattr(param.default, "description") and param.default.description:
                    desc = param.default.description

                params.append(
                    ParameterInfo(
                        name=param_name,
                        type_annotation=type_str,
                        default=default,
                        description=desc,
                    )
                )

            return_annotation = type_hints.get("return", sig.return_annotation)
            return_type = _python_type_name(return_annotation)

            tools.append(
                ToolInfo(
                    name=name,
                    description=description,
                    parameters=params,
                    return_type=return_type,
                )
            )

        return tools
