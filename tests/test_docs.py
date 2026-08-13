"""Guards against documentation drifting away from the code it describes.

These live as tests rather than as review guidance because a test runs for every
contributor on every PR, whether or not they use an agent. Both failures they catch
have happened: #64 shipped a CLI reference missing several flags, and AGENTS.md
referenced a path that had moved.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest
from typer.main import get_command

from intpot.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent

# Typer generates these; they are not intpot's interface to document.
_GENERATED_FLAGS = {"--help", "--install-completion", "--show-completion"}


def _cli_flags() -> list[tuple[str, str]]:
    """Every long option the CLI exposes, as (command path, flag)."""
    found: list[tuple[str, str]] = []

    def walk(command: click.Command, path: list[str]) -> None:
        for param in command.params:
            for opt in getattr(param, "opts", []):
                if opt.startswith("--") and opt not in _GENERATED_FLAGS:
                    found.append((" ".join(path), opt))
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                walk(sub, [*path, name])

    walk(get_command(app), ["intpot"])
    return sorted(set(found))


@pytest.mark.parametrize(("command", "flag"), _cli_flags())
def test_readme_documents_every_cli_flag(command: str, flag: str) -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    # Whole-token match: `--to` must not be satisfied by `--total`, and a flag
    # documented in prose ("`intpot --version`") counts as documented.
    pattern = rf"(?<![\w-]){re.escape(flag)}(?![\w-])"
    assert re.search(pattern, readme), (
        f"`{command} {flag}` is not mentioned in README.md. "
        f"Add it to the CLI Reference section."
    )


# A backticked token is treated as a repo path if it looks like one. Prose and
# code samples in the README use plenty of paths that intentionally don't exist
# (`app.py`, `mcp_server.py`), so only the two contributor-facing docs are checked.
_DOC_FILES = ("AGENTS.md", "CONTRIBUTING.md")

# Paths in AGENTS.md's layout table are relative to the package, not the repo.
_PATH_ROOTS = (Path(), Path("src/intpot"))

_PATH_TOKEN = re.compile(r"`([A-Za-z0-9_.*/-]+/[A-Za-z0-9_.*/-]*)`")


def _documented_paths() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name in _DOC_FILES:
        text = (REPO_ROOT / name).read_text()
        for token in _PATH_TOKEN.findall(text):
            if token.startswith(("http", "//")):
                continue
            found.append((name, token))
    return sorted(set(found))


@pytest.mark.parametrize(("doc", "token"), _documented_paths())
def test_docs_reference_only_paths_that_exist(doc: str, token: str) -> None:
    for root in _PATH_ROOTS:
        base = REPO_ROOT / root
        if "*" in token:
            if any(base.glob(token)):
                return
        elif (base / token).exists():
            return
    tried = " or ".join(str(r) if str(r) != "." else "<repo root>" for r in _PATH_ROOTS)
    pytest.fail(f"{doc} references `{token}`, which does not exist under {tried}")
