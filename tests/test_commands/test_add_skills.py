"""Tests for the `intpot add skills` command."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from intpot.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Auto-detect tests
# ---------------------------------------------------------------------------


def test_add_skills_auto_detect_claude(tmp_path: Path, monkeypatch):
    """Auto-detect Claude Code when .claude/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "claude" in result.output

    assert (tmp_path / ".claude" / "skills" / "intpot-cli.md").exists()
    assert (tmp_path / ".claude" / "skills" / "intpot-python.md").exists()

    cli_content = (tmp_path / ".claude" / "skills" / "intpot-cli.md").read_text()
    assert "intpot" in cli_content
    assert "intpot to cli" in cli_content

    py_content = (tmp_path / ".claude" / "skills" / "intpot-python.md").read_text()
    assert "intpot.load" in py_content


def test_add_skills_auto_detect_cursor(tmp_path: Path, monkeypatch):
    """Auto-detect Cursor when .cursor/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "cursor" in result.output

    cli_path = tmp_path / ".cursor" / "rules" / "intpot-cli.mdc"
    assert cli_path.exists()
    content = cli_path.read_text()
    assert "---" in content  # frontmatter
    assert "alwaysApply: false" in content
    assert "globs:" in content


def test_add_skills_auto_detect_windsurf(tmp_path: Path, monkeypatch):
    """Auto-detect Windsurf when .windsurf/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".windsurf").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "windsurf" in result.output
    assert (tmp_path / ".windsurf" / "rules" / "intpot-cli.md").exists()
    assert (tmp_path / ".windsurf" / "rules" / "intpot-python.md").exists()


def test_add_skills_auto_detect_copilot(tmp_path: Path, monkeypatch):
    """Auto-detect Copilot when .github/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "copilot" in result.output

    instructions = tmp_path / ".github" / "copilot-instructions.md"
    assert instructions.exists()
    content = instructions.read_text()
    assert "intpot" in content
    assert "<!-- intpot:" in content


def test_add_skills_auto_detect_cline(tmp_path: Path, monkeypatch):
    """Auto-detect Cline when .clinerules/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".clinerules").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "cline" in result.output
    assert (tmp_path / ".clinerules" / "intpot-cli.md").exists()
    assert (tmp_path / ".clinerules" / "intpot-python.md").exists()


def test_add_skills_auto_detect_codex(tmp_path: Path, monkeypatch):
    """Auto-detect Codex when AGENTS.md exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# Existing agents\n")

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "codex" in result.output

    content = (tmp_path / "AGENTS.md").read_text()
    assert "# Existing agents" in content  # preserved
    assert "intpot" in content


# ---------------------------------------------------------------------------
# Explicit --agent tests
# ---------------------------------------------------------------------------


def test_add_skills_explicit_agent(tmp_path: Path, monkeypatch):
    """--agent flag creates skills even without marker dirs."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["add", "skills", "--agent", "claude"])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "skills" / "intpot-cli.md").exists()


def test_add_skills_explicit_path(tmp_path: Path):
    """--path flag targets a specific directory."""
    target = tmp_path / "myproject"
    target.mkdir()

    result = runner.invoke(
        app, ["add", "skills", "--agent", "cursor", "--path", str(target)]
    )
    assert result.exit_code == 0
    assert (target / ".cursor" / "rules" / "intpot-cli.mdc").exists()


# ---------------------------------------------------------------------------
# Multi-agent detection
# ---------------------------------------------------------------------------


def test_add_skills_multiple_agents(tmp_path: Path, monkeypatch):
    """Detect and install for multiple agents at once."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "claude" in result.output
    assert "cursor" in result.output
    assert (tmp_path / ".claude" / "skills" / "intpot-cli.md").exists()
    assert (tmp_path / ".cursor" / "rules" / "intpot-cli.mdc").exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_add_skills_no_agents_detected(tmp_path: Path, monkeypatch):
    """Exit with error when no agents detected and no --agent given."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 1
    assert "No AI coding agents detected" in result.output


def test_add_skills_idempotent_copilot(tmp_path: Path, monkeypatch):
    """Running twice doesn't duplicate Copilot instructions."""
    monkeypatch.chdir(tmp_path)

    result1 = runner.invoke(app, ["add", "skills", "--agent", "copilot"])
    assert result1.exit_code == 0

    result2 = runner.invoke(app, ["add", "skills", "--agent", "copilot"])
    assert result2.exit_code == 0
    assert "already installed" in result2.output

    content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
    assert content.count("<!-- intpot: intpot CLI -->") == 1


def test_add_skills_idempotent_codex(tmp_path: Path, monkeypatch):
    """Running twice doesn't duplicate Codex AGENTS.md content."""
    monkeypatch.chdir(tmp_path)

    result1 = runner.invoke(app, ["add", "skills", "--agent", "codex"])
    assert result1.exit_code == 0

    result2 = runner.invoke(app, ["add", "skills", "--agent", "codex"])
    assert result2.exit_code == 0
    assert "already installed" in result2.output

    content = (tmp_path / "AGENTS.md").read_text()
    assert content.count("# intpot CLI") == 1


def test_add_skills_invalid_path(tmp_path: Path):
    """Error when --path doesn't exist or is not a directory."""
    result = runner.invoke(
        app, ["add", "skills", "--agent", "claude", "--path", "/nonexistent/path"]
    )
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_add_skills_claude_content_quality(tmp_path: Path, monkeypatch):
    """Verify Claude skill content has all essential info."""
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["add", "skills", "--agent", "claude"])

    cli_content = (tmp_path / ".claude" / "skills" / "intpot-cli.md").read_text()
    # Must have the key commands
    assert "intpot init" in cli_content
    assert "intpot to cli" in cli_content
    assert "intpot to mcp" in cli_content
    assert "intpot to api" in cli_content
    assert "--output" in cli_content
    assert "--dry-run" in cli_content

    py_content = (tmp_path / ".claude" / "skills" / "intpot-python.md").read_text()
    assert "intpot.load" in py_content
    assert "IntpotApp" in py_content
    assert ".to_cli()" in py_content
    assert ".to_mcp()" in py_content
    assert ".to_api()" in py_content
    assert ".write(" in py_content
    assert "inspect_app" in py_content
