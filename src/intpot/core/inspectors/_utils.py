"""Shared utilities for inspectors."""

from __future__ import annotations

import inspect
from typing import Any


def python_type_name(annotation: Any) -> str:
    """Convert a type annotation to a string representation."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return "str"
    if isinstance(annotation, type):
        return annotation.__name__
    # For typing generics (e.g. list[str], Optional[int]), use str()
    # but clean up the 'typing.' prefix for readability
    text = str(annotation)
    text = text.replace("typing.", "")
    return text
