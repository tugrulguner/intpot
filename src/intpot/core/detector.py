"""Auto-detect source type by importing a module and finding the app instance."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

from intpot.core.models import SourceType

_FRAMEWORK_CONSTRUCTORS = {"FastMCP", "Typer", "FastAPI"}


class DetectionError(Exception):
    pass


class SourceImportError(DetectionError):
    """The source file was found and looked like an app, but importing it failed.

    Distinct from "this file is not an app": the user's own module raised.
    Subclassing DetectionError means every command that already handles a
    detection failure reports this cleanly instead of dumping a traceback —
    but anything that needs to tell the two apart must catch this *first*,
    since a subclass matches its parent.
    """


_EXTRA_FOR_MODULE = {"fastmcp": "mcp", "fastapi": "api", "uvicorn": "api"}


def _import_failure_message(source_path: Path, exc: BaseException) -> str:
    """Explain an import failure in terms the user can act on."""
    if isinstance(exc, SystemExit):
        return (
            f"Cannot import {source_path}: it called sys.exit({exc.code!r}) while "
            f"being imported. Detection has to import the file, so module-level "
            f"exits run too — guard them with `if __name__ == '__main__':`."
        )
    detail = f"Cannot import {source_path}: {type(exc).__name__}: {exc}"
    missing = (
        getattr(exc, "name", None) if isinstance(exc, ModuleNotFoundError) else None
    )
    # Match the top-level module exactly. Substring matching claimed a missing
    # `myfastapi_helper` was FastAPI and sent the user to install intpot[api],
    # which would not have helped and hid the real cause.
    extra = _EXTRA_FOR_MODULE.get((missing or "").split(".", 1)[0])
    if extra:
        return f"{detail}\nInstall it with: pip install intpot[{extra}]"
    if missing:
        return (
            f"{detail}\nIf it is a module beside your source, intpot imports the "
            f"file directly and does not add its directory to sys.path."
        )
    return detail


def _has_framework_app_ast(source_path: Path) -> bool:
    """Check if a Python file contains a framework app assignment using AST.

    Looks for module-level assignments where the RHS is a Call to one of the
    known framework constructors (FastMCP, Typer, FastAPI).
    Returns False on syntax errors or files that don't contain such assignments.
    """
    try:
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        # Returning False here reported malformed Python as "no app instance
        # found" — the same message a perfectly valid non-app file gets — and a
        # directory scan skipped it without a word. A file that cannot be parsed
        # is broken, not uninteresting, and the user is the only one who can
        # fix it.
        raise SourceImportError(
            f"Cannot parse {source_path}: {type(exc).__name__}: {exc}"
        ) from exc

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        if isinstance(value, ast.Call):
            func = value.func
            # Handle direct calls like FastAPI() or Typer()
            if isinstance(func, ast.Name) and func.id in _FRAMEWORK_CONSTRUCTORS:
                return True
            # Handle attribute calls like fastapi.FastAPI() or typer.Typer()
            if isinstance(func, ast.Attribute) and func.attr in _FRAMEWORK_CONSTRUCTORS:
                return True
    return False


def _import_module_from_path(source_path: Path) -> Any:
    """Import a Python module from a file path."""
    # Use the full resolved path to avoid collisions between same-named files
    path_hash = abs(hash(str(source_path.resolve())))
    unique_name = f"_intpot_source_{source_path.stem}_{path_hash}"
    spec = importlib.util.spec_from_file_location(unique_name, source_path)
    if spec is None or spec.loader is None:
        raise DetectionError(f"Cannot load module from {source_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module
    try:
        spec.loader.exec_module(module)
    except (Exception, SystemExit) as exc:
        # The user's own module raised. Every command funnels through here, so
        # wrapping once is what stops a traceback reaching the terminal.
        #
        # SystemExit is listed separately because it derives from BaseException,
        # not Exception: a source calling sys.exit() at import — argparse on a
        # bad parse does exactly this — otherwise propagated, and intpot exited
        # with the source's own code and printed nothing at all. Catching
        # BaseException instead would also swallow KeyboardInterrupt.
        raise SourceImportError(_import_failure_message(source_path, exc)) from exc
    finally:
        # Clean up sys.modules to avoid leaking imported modules
        sys.modules.pop(unique_name, None)
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

    if not _has_framework_app_ast(source_path):
        raise DetectionError(
            f"No FastMCP, Typer, or FastAPI app instance found in {source_path}"
        )

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


def detect_instance(obj: Any) -> tuple[SourceType, Any]:
    """Detect source type from a live app instance."""
    if _is_fastmcp(obj):
        return SourceType.MCP, obj
    if _is_typer(obj):
        return SourceType.CLI, obj
    if _is_fastapi(obj):
        return SourceType.API, obj
    raise DetectionError(f"Unrecognized app type: {type(obj).__name__}")
