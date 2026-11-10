"""Create a persistent MCP project, install project-local agent guidance, and discover its tools.

Run with intpot[all] installed in this Python environment:
    python examples/project_workflow.py --output-dir ./my-new-project
Only the new output project is modified. Existing destinations are refused.
"""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    project = args.output_dir.absolute()
    if project.exists() or project.is_symlink():
        parser.error(f"Destination already exists: {project}")
    cli = shutil.which("intpot", path=str(Path(sys.executable).parent))
    if cli is None:
        parser.error("Install intpot[all] in this Python environment first.")
    project.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [cli, "init", project.name, "--type", "mcp"], cwd=project.parent, check=True
    )
    # Select split project-local skills explicitly; do not auto-detect an agent.
    subprocess.run(
        [cli, "add", "skills", "--agent", "claude", "--path", str(project)], check=True
    )
    # Discovery imports Python files. Scan only this fresh, trusted scaffold.
    discovery = subprocess.run(
        [cli, "inspect", str(project), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    (project / "discovery.json").write_text(discovery.stdout, encoding="utf-8")
    print(discovery.stdout, end="")
    print(f"Project: {project}")
    print("Guidance: .claude/skills/; inventory: discovery.json")
    print(
        "Start the native stdio MCP server: "
        + shlex.join([sys.executable, str(project / "server.py")])
    )


if __name__ == "__main__":
    main()
