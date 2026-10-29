"""Release boundaries for verified original body-reference ranges."""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "relative", ["examples/reference_locations.py", "examples/README.md"]
)
def test_occurrence_example_minimum_release_is_explicit(relative):
    text = (ROOT / relative).read_text()
    assert "requires v0.16.0 or newer" in text
    assert "until publication" in text.lower()
    assert "source-checkout-only (unreleased)" not in text
    assert "unreleased source checkout only" not in text


def test_roadmap_keeps_occurrences_separate_from_richer_dependencies():
    text = (ROOT / "ROADMAP.md").read_text()
    assert "## v0.16 — Current foundation" in text
    assert "v0.16.0 release candidate" in text
    assert "plain-body" in text
    assert "(unreleased)" not in text
    assert "richer evaluation-order dependency edges remain separate" in text
    assert "The v0.15.0 release adds bounded static binding paths" in text


def test_release_version_matches_lock_root():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    assert project["project"]["version"] == "0.16.0"
    assert (
        next(p for p in lock["package"] if p["name"] == "intpot")["version"] == "0.16.0"
    )


def test_changelog_includes_bounded_occurrence_feature():
    text = (ROOT / "CHANGELOG.md").read_text()
    section = text.split("## [0.16.0]", 1)[1].split("\n## [", 1)[0]
    assert "identifier ranges" in section
    assert "unavailable" in section and "refusals stay unchanged" in section
