"""Skill content templates for different AI coding agents."""

from __future__ import annotations

from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "templates" / "skills"


def _read_skill(name: str) -> str:
    """Read a skill markdown template from the templates/skills/ directory."""
    return (_SKILLS_DIR / name).read_text()


def cli_skill_body() -> str:
    """Return the CLI skill content."""
    return _read_skill("intpot-cli.md")


def python_skill_body() -> str:
    """Return the Python API skill content."""
    return _read_skill("intpot-python.md")


# ---------------------------------------------------------------------------
# Agent-specific formatters
# ---------------------------------------------------------------------------


def claude_skill(title: str, body: str, *, name: str, description: str) -> str:
    """Format as a Claude Code skill (.claude/skills/<name>/SKILL.md).

    Claude Code discovers a skill by its YAML frontmatter: `name` identifies it
    and `description` is what the model reads to decide whether the skill is
    relevant. A file without frontmatter is never loaded, so the body alone --
    which is what this used to return -- was silently inert.
    """
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


def cursor_rule(title: str, body: str, globs: str = '["*.py"]') -> str:
    """Format as a Cursor rule (.mdc in .cursor/rules/)."""
    return (
        f"---\n"
        f"description: {title} — use intpot to convert between CLI, MCP, and API frameworks\n"
        f"globs: {globs}\n"
        f"alwaysApply: false\n"
        f"---\n\n"
        f"{body}"
    )


def windsurf_rule(title: str, body: str) -> str:
    """Format as a Windsurf rule (.md in .windsurf/rules/)."""
    return body


def copilot_instruction(title: str, body: str) -> str:
    """Format for GitHub Copilot (.github/copilot-instructions.md)."""
    return f"\n<!-- intpot: {title} -->\n\n{body}\n"


def cline_rule(title: str, body: str) -> str:
    """Format as a Cline rule (.md in .clinerules/)."""
    return body


def codex_instruction(title: str, body: str) -> str:
    """Format for OpenAI Codex CLI (AGENTS.md)."""
    return body
