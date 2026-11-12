"""Keep shipped collection guidance aligned with the qualified subset."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from intpot.cli import app
from intpot.skills.content import cli_skill_body, python_skill_body


def assert_outer_optional_guidance(text: str) -> None:
    text = " ".join(text.split())
    assert "Outer `Optional[list[str]]` repeatable options are supported." in text
    assert (
        "Optional `Optional[list[str]]` collections are still in progress" not in text
    )
    assert (
        "forms, optional repeatable collections wrapped in `Optional[...]`" not in text
    )
    # Do not repair the false denial by losing the real boundaries.
    for boundary in (
        "Required repeatable options",
        "nullable elements",
        "parser",
        "factory",
    ):
        assert boundary in text
    assert "not in public v0.16.0" in text or "absent from public v0.16.0" in text


@pytest.mark.parametrize("body", [cli_skill_body, python_skill_body])
def test_shipped_skills_qualify_outer_optional_repeatable_strings(body) -> None:
    assert_outer_optional_guidance(body())


def test_installed_codex_guidance_qualifies_outer_optional_repeatable_strings(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        app, ["add", "skills", "--agent", "codex", "--path", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    installed = (tmp_path / "AGENTS.md").read_text()
    assert_outer_optional_guidance(installed)
