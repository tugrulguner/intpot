"""Shared fixtures for intpot tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_source(tmp_path: Path):
    """Factory fixture: write a source file and return its path."""

    def _write(content: str, name: str = "source.py") -> Path:
        p = tmp_path / name
        p.write_text(textwrap.dedent(content))
        return p

    return _write
