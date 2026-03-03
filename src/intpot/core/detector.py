"""Auto-detect source type by importing a module and finding the app instance."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from intpot.core.models import SourceType


class DetectionError(Exception):
    pass


def _import_module_from_path(source_path: Path) -> Any:
    """Import a Python module from a file path."""
    module_name = source_path.stem
    # Avoid name collisions with already-imported modules
    unique_name = f"_intpot_source_{module_name}"
    spec = importlib.util.spec_from_file_location(unique_name, source_path)
    if spec is None or spec.loader is None:
        raise DetectionError(f"Cannot load module from {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


def _is_fastmcp(obj: Any) -> bool:
    cls_name = type(obj).__name__
    module = type(obj).__module__ or ""
    return cls_name == "FastMCP" and "fastmcp" in module


def _is_typer(obj: Any) -> bool:
    cls_name = type(obj).__name__
    module = type(obj).__module__ or ""
    return cls_name == "Typer" and "typer" in module


def _is_fastapi(obj: Any) -> bool:
    cls_name = type(obj).__name__
    module = type(obj).__module__ or ""
    return cls_name == "FastAPI" and "fastapi" in module


def detect_source(source_path: Path) -> tuple[SourceType, Any]:
    """Detect the source type and return (source_type, app_instance).

    Scans module-level variables for known app instances.
    """
    source_path = Path(source_path).resolve()
    if not source_path.exists():
        raise DetectionError(f"File not found: {source_path}")

    module = _import_module_from_path(source_path)

    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        obj = getattr(module, attr_name)
        if _is_fastmcp(obj):
            return SourceType.MCP, obj
        if _is_typer(obj):
            return SourceType.CLI, obj
        if _is_fastapi(obj):
            return SourceType.API, obj

    raise DetectionError(
        f"No FastMCP, Typer, or FastAPI app instance found in {source_path}"
    )
