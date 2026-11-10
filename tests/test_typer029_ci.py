from __future__ import annotations

from pathlib import Path


def test_ci_exercises_typer_029_representation_regressions() -> None:
    text = (Path(__file__).parents[1] / ".github/workflows/ci.yml").read_text()
    assert "name: Typer 0.29.0" in text
    assert '--with "typer==0.29.0"' in text
    assert "tests/test_typer029_compatibility.py" in text
