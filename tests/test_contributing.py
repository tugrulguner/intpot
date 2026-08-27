"""Contract tests for contributor entry points and templates."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AGENT_GUIDE = ROOT / "AGENTS.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
REVIEWING = ROOT / "docs" / "reviewing.md"
ISSUE_FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
PULL_REQUEST_TEMPLATE = ROOT / ".github" / "pull_request_template.md"
CHANGELOG_GUIDE = ROOT / "changelog.d" / "README.md"
CHANGELOG_WORKFLOW = ROOT / ".github" / "workflows" / "changelog.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_issue_forms_define_intpot_reporting_contract() -> None:
    bug = _text(ISSUE_FORMS / "bug.yml")
    feature = _text(ISSUE_FORMS / "feature.yml")
    chooser = _text(ISSUE_FORMS / "config.yml")

    for field in (
        "Current behavior",
        "Expected behavior",
        "Minimal reproduction",
        "Source and target frameworks",
        "Intpot version or source revision",
        "Framework versions",
        "Generated artifact or command output",
        "Contribution intent",
    ):
        assert field in bug
    assert "removed credentials" in bug

    for field in (
        "Problem",
        "What happens now",
        "Why I want it",
        "Concrete use case",
        "Proposed solution",
        "Acceptance criteria",
        "Open question",
        "Implementation notes",
        "Alternatives considered",
        "Scope and non-goals",
        "Contribution intent",
    ):
        assert field in feature
    assert "inspector, `ToolInfo`, generator, and runtime boundaries" in feature

    assert "blank_issues_enabled: false" in chooser
    assert "/discussions/categories/q-a" in chooser
    assert "/discussions/categories/ideas-roadmap" in chooser


def test_issue_forms_parse_and_have_unique_field_ids() -> None:
    for name in ("bug.yml", "feature.yml"):
        form = yaml.safe_load(_text(ISSUE_FORMS / name))
        ids = [item["id"] for item in form["body"] if "id" in item]

        assert ids
        assert len(ids) == len(set(ids))


def test_pull_request_template_requires_classification_and_evidence() -> None:
    template = _text(PULL_REQUEST_TEMPLATE)

    for heading in (
        "## Summary and motivation",
        "## Related issue or direct-PR reason",
        "## Scope and non-goals",
        "## Safety and compatibility",
        "## Verification and behavioral evidence",
        "## Generated artifact evidence",
        "## Documentation and changelog",
        "## Reviewer guidance",
    ):
        assert heading in template
    assert "Closes #<issue-number>" in template
    assert "make check" in template
    assert "make build" in template
    assert "execute generated output" in template


def test_contributor_journey_classifies_work_before_implementation() -> None:
    contributing = _text(CONTRIBUTING)

    assert "Substantial contract work: open an issue first" in contributing
    assert "Small direct changes" in contributing
    assert "Questions and early ideas" in contributing
    assert "Claimed community work" in contributing
    assert "comment and wait for confirmation" in contributing
    assert "Closes #<issue-number>" in contributing
    assert "reviewer can reproduce" in contributing


def test_reviewing_requires_exact_heads_and_behavioral_evidence() -> None:
    reviewing = _text(REVIEWING)

    assert "Pin the exact head" in reviewing
    assert "reviewed head SHA" in reviewing
    assert "execute the generated artifact" in reviewing
    assert "A passing compile step is not behavioral evidence" in reviewing
    assert "current main" in reviewing


def test_changelog_contract_uses_issues_or_generated_orphans() -> None:
    agent_guide = _text(AGENT_GUIDE)
    contributing = _text(CONTRIBUTING)
    template = _text(PULL_REQUEST_TEMPLATE)
    guide = _text(CHANGELOG_GUIDE)
    workflow = _text(CHANGELOG_WORKFLOW)
    config = tomllib.loads(_text(ROOT / "pyproject.toml"))["tool"]["towncrier"]

    for document in (agent_guide, contributing, guide):
        assert "<issue-number>.<type>.md" in document
        assert "towncrier create +.changed.md" in document
    assert "<issue-number>.<type>.md" in template
    assert "+<identifier>.<type>.md" in template

    assert "\\+[A-Za-z0-9]" in workflow
    assert 'select(.status != "removed") | .filename' in workflow
    assert "issues: read" in workflow
    assert "issues/${issue_number}" in workflow
    assert "must use an issue number" in workflow
    assert "pull/{issue}" not in config["issue_format"]
    assert config["issue_format"].endswith("/issues/{issue})")


def test_contribution_document_links_resolve() -> None:
    documents = (CONTRIBUTING, REVIEWING, CHANGELOG_GUIDE, PULL_REQUEST_TEMPLATE)
    markdown_link = re.compile(r"\[[^]]+\]\(([^)]+)\)")

    for document in documents:
        for target in markdown_link.findall(_text(document)):
            if target.startswith(("http://", "https://", "#")) or "<" in target:
                continue
            path_text = target.split("#", 1)[0]
            if not path_text:
                continue
            assert (document.parent / path_text).resolve().exists(), (
                f"{document.relative_to(ROOT)} links to missing path {target}"
            )
