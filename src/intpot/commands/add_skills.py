"""Install intpot skills/rules into AI coding agent config directories."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import typer

from intpot.core.models import Agent
from intpot.skills.content import (
    claude_skill,
    cli_skill_body,
    cline_rule,
    codex_instruction,
    copilot_instruction,
    cursor_rule,
    python_skill_body,
    windsurf_rule,
)

# ---------------------------------------------------------------------------
# Per-agent writers
# ---------------------------------------------------------------------------

_CLAUDE_SKILLS = (
    (
        "intpot-cli",
        "intpot CLI",
        cli_skill_body,
        "Convert Python apps between Typer (CLI), FastMCP (MCP) and FastAPI, or "
        "serve one set of tools as all three, using the intpot command line. Use "
        "when asked to turn a CLI into an MCP server or REST API, to expose "
        "functions to an agent, or to scaffold a CLI/MCP/API project.",
    ),
    (
        "intpot-python",
        "intpot Python API",
        python_skill_body,
        "Use intpot programmatically: define tools once with intpot.App and serve "
        "or eject them as Typer/FastAPI/FastMCP, or convert existing apps with "
        "intpot.load(). Use when writing scripts, build steps or CI that need "
        "framework conversion rather than the intpot command line.",
    ),
)


def _write_claude(root: Path) -> list[Path]:
    """Write Claude Code skills to .claude/skills/<name>/SKILL.md.

    Claude Code looks for a directory per skill containing SKILL.md, and reads
    the YAML frontmatter to discover it. A flat .md file is never loaded.
    """
    skills_root = root / ".claude" / "skills"
    written: list[Path] = []

    for name, title, body, description in _CLAUDE_SKILLS:
        skill_dir = skills_root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "SKILL.md"
        path.write_text(claude_skill(title, body(), name=name, description=description))
        written.append(path)

    return written


def _write_cursor(root: Path) -> list[Path]:
    """Write Cursor rules to .cursor/rules/."""
    rules_dir = root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    cli_path = rules_dir / "intpot-cli.mdc"
    cli_path.write_text(cursor_rule("intpot CLI", cli_skill_body()))
    written.append(cli_path)

    py_path = rules_dir / "intpot-python.mdc"
    py_path.write_text(cursor_rule("intpot Python API", python_skill_body()))
    written.append(py_path)

    return written


def _write_windsurf(root: Path) -> list[Path]:
    """Write Windsurf rules to .windsurf/rules/."""
    rules_dir = root / ".windsurf" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    cli_path = rules_dir / "intpot-cli.md"
    cli_path.write_text(windsurf_rule("intpot CLI", cli_skill_body()))
    written.append(cli_path)

    py_path = rules_dir / "intpot-python.md"
    py_path.write_text(windsurf_rule("intpot Python API", python_skill_body()))
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

    combined = copilot_instruction(
        "intpot CLI", cli_skill_body()
    ) + copilot_instruction("intpot Python API", python_skill_body())

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
    cli_path.write_text(cline_rule("intpot CLI", cli_skill_body()))
    written.append(cli_path)

    py_path = rules_dir / "intpot-python.md"
    py_path.write_text(cline_rule("intpot Python API", python_skill_body()))
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
        codex_instruction("intpot CLI", cli_skill_body())
        + "\n"
        + codex_instruction("intpot Python API", python_skill_body())
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

# Paths whose presence means the agent is actually configured for this project.
# These are deliberately specific. `.github/` only means the project is on
# GitHub, and a bare `AGENTS.md` is a cross-tool convention that most repos now
# have for reasons unrelated to Codex — detecting on either matched ordinary
# repositories using no agent at all, and both writers *append*, so a plain CI
# repo had hundreds of lines added to its own AGENTS.md.
_AGENT_MARKERS: dict[Agent, str] = {
    Agent.claude: ".claude",
    Agent.cursor: ".cursor",
    Agent.windsurf: ".windsurf",
    Agent.copilot: ".github/copilot-instructions.md",
    Agent.cline: ".clinerules",
}

# Codex reads AGENTS.md, but so does nearly everything else, so its presence is
# not evidence of Codex. There is no project-level marker that is: the Codex CLI
# keeps its configuration in the user's home directory. Ask for it by name.
_REQUIRES_EXPLICIT_REQUEST = (Agent.codex,)


def _detect_agents(root: Path) -> list[Agent]:
    """Auto-detect which agents are configured in the project.

    Only agents with an unambiguous project-level marker are detected. Missing
    one is recoverable with --agent; guessing wrong silently edits files the
    user never asked to touch.
    """
    return [
        agent for agent, marker in _AGENT_MARKERS.items() if (root / marker).exists()
    ]


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
            explicit = ", ".join(a.value for a in _REQUIRES_EXPLICIT_REQUEST)
            typer.echo(
                "No AI coding agents detected. Use --agent to specify one "
                "(claude, cursor, windsurf, copilot, cline, codex).\n"
                f"Note: {explicit} is never auto-detected — AGENTS.md is a "
                "cross-tool convention, so its presence does not imply it.",
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
