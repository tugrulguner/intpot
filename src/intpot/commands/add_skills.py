"""Install intpot skills/rules into AI coding agent config directories."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from collections.abc import Callable

import typer

from intpot.skills.content import (
    CLI_SKILL_BODY,
    PYTHON_SKILL_BODY,
    claude_skill,
    cline_rule,
    codex_instruction,
    copilot_instruction,
    cursor_rule,
    windsurf_rule,
)

# ---------------------------------------------------------------------------
# Agent enum
# ---------------------------------------------------------------------------


class Agent(str, Enum):
    claude = "claude"
    cursor = "cursor"
    windsurf = "windsurf"
    copilot = "copilot"
    cline = "cline"
    codex = "codex"


# ---------------------------------------------------------------------------
# Per-agent writers
# ---------------------------------------------------------------------------

_WRITERS: dict[Agent, tuple] = {}  # populated below


def _write_claude(root: Path) -> list[Path]:
    """Write Claude Code skills to .claude/skills/."""
    skills_dir = root / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    cli_path = skills_dir / "intpot-cli.md"
    cli_path.write_text(claude_skill("intpot CLI", CLI_SKILL_BODY))
    written.append(cli_path)

    py_path = skills_dir / "intpot-python.md"
    py_path.write_text(claude_skill("intpot Python API", PYTHON_SKILL_BODY))
    written.append(py_path)

    return written


def _write_cursor(root: Path) -> list[Path]:
    """Write Cursor rules to .cursor/rules/."""
    rules_dir = root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    cli_path = rules_dir / "intpot-cli.mdc"
    cli_path.write_text(cursor_rule("intpot CLI", CLI_SKILL_BODY))
    written.append(cli_path)

    py_path = rules_dir / "intpot-python.mdc"
    py_path.write_text(cursor_rule("intpot Python API", PYTHON_SKILL_BODY))
    written.append(py_path)

    return written


def _write_windsurf(root: Path) -> list[Path]:
    """Write Windsurf rules to .windsurf/rules/."""
    rules_dir = root / ".windsurf" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    cli_path = rules_dir / "intpot-cli.md"
    cli_path.write_text(windsurf_rule("intpot CLI", CLI_SKILL_BODY))
    written.append(cli_path)

    py_path = rules_dir / "intpot-python.md"
    py_path.write_text(windsurf_rule("intpot Python API", PYTHON_SKILL_BODY))
    written.append(py_path)

    return written


def _write_copilot(root: Path) -> list[Path]:
    """Append intpot instructions to .github/copilot-instructions.md."""
    gh_dir = root / ".github"
    gh_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    instructions_path = gh_dir / "copilot-instructions.md"
    marker = "<!-- intpot: intpot CLI -->"

    existing = instructions_path.read_text() if instructions_path.exists() else ""

    if marker in existing:
        # Already installed — skip to avoid duplicates
        return written

    combined = copilot_instruction("intpot CLI", CLI_SKILL_BODY) + copilot_instruction(
        "intpot Python API", PYTHON_SKILL_BODY
    )

    with instructions_path.open("a") as f:
        f.write(combined)

    written.append(instructions_path)
    return written


def _write_cline(root: Path) -> list[Path]:
    """Write Cline rules to .clinerules/."""
    rules_dir = root / ".clinerules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    cli_path = rules_dir / "intpot-cli.md"
    cli_path.write_text(cline_rule("intpot CLI", CLI_SKILL_BODY))
    written.append(cli_path)

    py_path = rules_dir / "intpot-python.md"
    py_path.write_text(cline_rule("intpot Python API", PYTHON_SKILL_BODY))
    written.append(py_path)

    return written


def _write_codex(root: Path) -> list[Path]:
    """Append intpot instructions to AGENTS.md (OpenAI Codex CLI)."""
    written: list[Path] = []
    agents_path = root / "AGENTS.md"
    marker = "# intpot CLI"

    existing = agents_path.read_text() if agents_path.exists() else ""

    if marker in existing:
        return written

    combined = (
        codex_instruction("intpot CLI", CLI_SKILL_BODY)
        + "\n"
        + codex_instruction("intpot Python API", PYTHON_SKILL_BODY)
    )

    with agents_path.open("a") as f:
        f.write(combined)

    written.append(agents_path)
    return written


_AGENT_WRITERS: dict[Agent, Callable[..., list[Path]]] = {
    Agent.claude: _write_claude,
    Agent.cursor: _write_cursor,
    Agent.windsurf: _write_windsurf,
    Agent.copilot: _write_copilot,
    Agent.cline: _write_cline,
    Agent.codex: _write_codex,
}

# Folders whose presence signals that an agent is in use
_AGENT_MARKERS: dict[Agent, str] = {
    Agent.claude: ".claude",
    Agent.cursor: ".cursor",
    Agent.windsurf: ".windsurf",
    Agent.copilot: ".github",
    Agent.cline: ".clinerules",
    Agent.codex: "AGENTS.md",
}


def _detect_agents(root: Path) -> list[Agent]:
    """Auto-detect which agents are configured in the project."""
    found: list[Agent] = []
    for agent, marker in _AGENT_MARKERS.items():
        if (root / marker).exists():
            found.append(agent)
    return found


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def add_skills(
    agent: Agent | None = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target agent (claude, cursor, windsurf, copilot, cline, codex). Auto-detects if omitted.",
    ),
    path: Path | None = typer.Option(
        None,
        "--path",
        "-p",
        help="Project root directory. Defaults to current directory.",
    ),
) -> None:
    """Install intpot skills/rules for AI coding agents.

    Auto-detects which agents are configured in the project, or specify
    one explicitly with --agent.
    """
    root = (path or Path.cwd()).resolve()

    if not root.is_dir():
        typer.echo(f"Path is not a directory: {root}", err=True)
        raise typer.Exit(1)

    if agent:
        agents = [agent]
    else:
        agents = _detect_agents(root)
        if not agents:
            typer.echo(
                "No AI coding agents detected. Use --agent to specify one "
                "(claude, cursor, windsurf, copilot, cline, codex).",
                err=True,
            )
            raise typer.Exit(1)

    total_written: list[Path] = []
    for ag in agents:
        writer = _AGENT_WRITERS[ag]
        written = writer(root)
        for p in written:
            rel = p.relative_to(root)
            typer.echo(f"  ✓ {rel}")
        total_written.extend(written)

    if total_written:
        typer.echo(
            f"\nInstalled intpot skills for {len(agents)} agent(s): "
            f"{', '.join(a.value for a in agents)}"
        )
    else:
        typer.echo("Skills already installed — no files changed.")
