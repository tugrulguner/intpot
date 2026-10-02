from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_demo_recorder_writes_provenance_and_real_interface_outputs(
    tmp_path: Path,
) -> None:
    output = tmp_path / "preview.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "record_demo_preview.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["source"] == "examples/semantic_schema.py"
    assert payload["source_sha256"]
    assert payload["intpot_version"]
    assert payload["execution"] == "live Intpot serve adapters exercised in-process"
    assert payload["examples"][0]["id"] == "greet"
    assert payload["examples"][0]["interfaces"] == {
        "cli": "Hello, Ada!\n",
        "api": "Hello, Ada!",
        "mcp": "Hello, Ada!",
    }
    assert payload["examples"][1]["interfaces"]["cli"] == "Hello, Ada\n"
