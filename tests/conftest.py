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


@pytest.fixture()
def callback_annotations_eager():
    """Probe actual annotation storage without evaluating an annotation provider."""

    def probe(value: bool):
        pass

    return getattr(probe, "__annotate__", None) is None


@pytest.fixture()
def eager_callback_annotations(callback_annotations_eager):
    """Positive capture cases require eager, provider-free callback annotations."""
    if not callback_annotations_eager:
        pytest.skip(
            "callback annotation providers are deliberately refused; eager capture unavailable"
        )
