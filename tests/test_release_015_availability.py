"""Availability regressions for the bounded binding-path release."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "relative", ["examples/binding_chains.py", "examples/README.md"]
)
def test_chain_example_minimum_version_is_explicit(relative):
    text = (ROOT / relative).read_text()
    assert "requires v0.15.0 or newer" in text
    assert "requires an unreleased source checkout" not in text
    assert "unreleased source checkout" not in text.splitlines()[0]
    assert "caller-authored" in text


def test_roadmap_distinguishes_binding_paths_from_richer_graphs():
    text = (ROOT / "ROADMAP.md").read_text()
    assert "## v0.15 — Current foundation" in text
    assert "The v0.15.0 release candidate adds bounded static binding paths" in text
    assert "richer evaluation-order dependency edges remain separate" in text
    assert "The next source slice (unreleased)" not in text
