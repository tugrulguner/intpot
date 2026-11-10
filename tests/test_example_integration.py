"""Keep user-facing capability scripts in the ordinary quality gates."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CAPABILITY_PATHS = (
    "examples/enum_export/",
    "examples/convert_enum_export.py",
    "examples/selected_tools.py",
    "examples/convert_selected_tools.py",
    "examples/convert_informational.py",
    "examples/call_converted_mcp.py",
    "examples/project_workflow.py",
)


@pytest.mark.parametrize("config", ["Makefile", ".github/workflows/ci.yml"])
def test_capability_scripts_are_in_every_lint_and_typecheck_lane(config: str) -> None:
    lines = (ROOT / config).read_text().splitlines()
    lanes = [
        line for line in lines if "uv run ruff " in line or "uv run pyright " in line
    ]
    assert len(lanes) >= 3
    for line in lanes:
        for path in CAPABILITY_PATHS:
            assert path in line, (config, path, line)


@pytest.mark.parametrize("guide", ["AGENTS.md", "src/intpot/AGENTS.md"])
def test_contributor_guidance_recognizes_published_reference_locations(
    guide: str,
) -> None:
    text = (ROOT / guide).read_text()
    assert "v0.16.0 release candidate" not in text
    assert "Exact body-reference locations (v0.16.0)" in text


def test_unselected_command_demonstrates_real_source_validation() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/selected_tools.py"),
            "guarded",
            "--value",
            "x",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "at least three" in result.stdout + result.stderr


@pytest.mark.parametrize(
    "recipe",
    ["convert_enum_export.py", "convert_selected_tools.py", "convert_informational.py"],
)
def test_printed_launch_command_preserves_a_spaced_output_path(
    recipe: str, tmp_path: Path
) -> None:
    import runpy
    import shlex

    if recipe == "convert_informational.py":
        source = runpy.run_path(str(ROOT / "examples/informational_text/app.py"))
        if callable(getattr(source["version_callback"], "__annotate__", None)):
            pytest.skip("informational parameter providers are intentionally refused")
    output = tmp_path / "generated servers"
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / recipe), "--output-dir", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    command = next(
        line.removeprefix("HTTP: ")
        for line in result.stdout.splitlines()
        if line.startswith("HTTP: ")
    )
    arguments = shlex.split(command)
    assert arguments[arguments.index("--app-dir") + 1] == str(output)


def test_mcp_example_client_calls_a_new_generated_server(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    generated = tmp_path / "selected"
    conversion = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/convert_selected_tools.py"),
            "--output-dir",
            str(generated),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert conversion.returncode == 0, conversion.stderr
    call = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/call_converted_mcp.py"),
            "selected",
            '{"text":"Hello World"}',
            "--server-dir",
            str(generated),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert call.returncode == 0, call.stdout + call.stderr
    assert call.stdout.strip() == "hello-world"
