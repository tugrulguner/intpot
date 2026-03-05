"""Discover convertible Python apps in a directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intpot.core.detector import DetectionError, detect_source
from intpot.core.models import SourceType

_SKIP_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".git",
    ".tox",
    ".mypy_cache",
}


def discover_sources(directory: Path) -> list[tuple[Path, SourceType, Any]]:
    """Scan a directory for Python files containing app instances.

    Returns list of (file_path, source_type, app_instance) tuples.
    Skips files that don't contain recognized frameworks.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        msg = f"Not a directory: {directory}"
        raise NotADirectoryError(msg)

    results: list[tuple[Path, SourceType, Any]] = []

    for py_file in sorted(directory.rglob("*.py")):
        # Skip hidden dirs and known non-source dirs
        if any(
            part.startswith(".") or part in _SKIP_DIRS
            for part in py_file.relative_to(directory).parts[:-1]
        ):
            continue

        try:
            source_type, app_instance = detect_source(py_file)
        except (DetectionError, SyntaxError, ImportError, OSError):
            continue

        results.append((py_file, source_type, app_instance))

    return results
