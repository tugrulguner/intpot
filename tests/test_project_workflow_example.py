"""Exercise the project-tooling teaching recipe through the real installed CLI."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

ROOT = Path(__file__).parents[1]


def test_project_workflow_creates_discovers_and_equips_a_real_project(
    tmp_path: Path,
) -> None:
    project = tmp_path / "new project"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    command = [
        sys.executable,
        str(ROOT / "examples/project_workflow.py"),
        "--output-dir",
        str(project),
    ]
    result = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=45
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "server.py").is_file()
    for name in ("intpot-cli", "intpot-python"):
        skill = project / ".claude" / "skills" / name / "SKILL.md"
        assert skill.is_file() and skill.read_text().startswith("---")
    discovery = json.loads((project / "discovery.json").read_text())
    assert len(discovery) == 1 and discovery[0]["type"] == "mcp"
    assert discovery[0]["tools"]
    assert Path(discovery[0]["source"]).resolve() == project / "server.py"

    async def call_scaffold() -> None:
        transport = PythonStdioTransport(
            project / "server.py", python_cmd=sys.executable, env=env
        )
        async with Client(transport) as client:
            result = await client.call_tool("hello", {"name": "Curiosity"})
            assert not result.is_error
            assert any(
                getattr(content, "text", None) == "Hello, Curiosity!"
                for content in result.content
            )

    asyncio.run(call_scaffold())
    before = {
        p.relative_to(project): p.read_bytes()
        for p in project.rglob("*")
        if p.is_file()
    }
    refused = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20
    )
    assert refused.returncode != 0 and "already exists" in refused.stderr
    assert before == {
        p.relative_to(project): p.read_bytes()
        for p in project.rglob("*")
        if p.is_file()
    }
