"""Install intpot skills/rules into AI coding agent config directories."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional

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

_MANAGED_START = "<!-- intpot:managed:start -->"
_MANAGED_END = "<!-- intpot:managed:end -->"
_CODEX_DEFAULT_MAX_BYTES = 32 * 1024

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
    """Install an updateable managed block in Copilot's instructions."""
    gh_dir = root / ".github"
    gh_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    instructions_path = gh_dir / "copilot-instructions.md"
    existing = instructions_path.read_text() if instructions_path.exists() else ""
    combined = copilot_instruction(
        "intpot CLI", cli_skill_body()
    ) + copilot_instruction("intpot Python API", python_skill_body())

    updated = _upsert_managed_block(
        existing,
        combined,
        legacy_start="<!-- intpot: intpot CLI -->",
    )
    if updated == existing:
        return written

    instructions_path.write_text(updated)

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
    """Install an updateable managed block in AGENTS.md for Codex CLI."""
    written: list[Path] = []
    agents_path = root / "AGENTS.md"
    existing = agents_path.read_text() if agents_path.exists() else ""
    combined = (
        codex_instruction("intpot CLI", cli_skill_body())
        + "\n"
        + codex_instruction("intpot Python API", python_skill_body())
    )

    updated = _upsert_managed_block(existing, combined, legacy_start="# intpot CLI")
    if updated != existing:
        agents_path.write_text(updated)
        written.append(agents_path)

    if len(updated.encode()) > _CODEX_DEFAULT_MAX_BYTES:
        typer.echo(
            "Warning: Codex AGENTS.md now exceeds the default 32 KiB instruction "
            "limit; Codex may truncate instructions unless its limit is increased.",
            err=True,
        )
    return written


def _upsert_managed_block(existing: str, content: str, *, legacy_start: str) -> str:
    """Insert or replace intpot's bounded block while preserving user text.

    Releases before managed blocks emitted only a start marker. For those files,
    the second skill heading and the next top-level heading provide a conservative
    boundary. A partial legacy install containing only its start marker replaces
    only that line rather than consuming user content after it.
    """
    block = f"{_MANAGED_START}\n\n{content.strip()}\n\n{_MANAGED_END}"

    search_from = 0
    while (start := existing.find(_MANAGED_START, search_from)) >= 0:
        next_start = existing.find(_MANAGED_START, start + len(_MANAGED_START))
        end = existing.find(_MANAGED_END, start + len(_MANAGED_START))
        if end >= 0 and (next_start < 0 or end < next_start):
            end += len(_MANAGED_END)
            return existing[:start] + block + existing[end:]
        search_from = next_start if next_start >= 0 else len(existing)

    if _MANAGED_START in existing:
        # Without an end marker there is no safe way to distinguish stale
        # generated text from user content. Preserve the file byte-for-byte and
        # append a valid block that future runs can update.
        return _append_managed_block(existing, block)

    start = existing.find(legacy_start)
    if start >= 0:
        end = _legacy_section_end(existing, start)
        if end is not None:
            return existing[:start] + block + existing[end:]
        return _append_managed_block(existing, block)

    return _append_managed_block(existing, block)


def _append_managed_block(existing: str, block: str) -> str:
    """Append a managed block without changing any existing bytes."""
    separator = "" if not existing or existing.endswith("\n\n") else "\n\n"
    return existing + separator + block + "\n"


def _legacy_section_end(text: str, start: int) -> int | None:
    """Find a safe boundary for an old unbounded installation, if one exists."""
    second_skill = text.find("# intpot Python API", start)
    if second_skill < 0:
        line_end = text.find("\n", start)
        if line_end < 0 or not text[line_end:].strip():
            return len(text)
        return None

    next_heading = text.find("\n# ", second_skill + len("# intpot Python API"))
    return None if next_heading < 0 else next_heading


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


# Typer 0.9 cannot parse PEP 604 unions in command parameter annotations.
def add_skills(
    agent: Optional[Agent] = typer.Option(  # noqa: UP045
        None,
        "--agent",
        "-a",
        help="Target agent (claude, cursor, windsurf, copilot, cline, codex). Auto-detects if omitted.",
    ),
    path: Optional[Path] = typer.Option(  # noqa: UP045
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
