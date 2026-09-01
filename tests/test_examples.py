"""Behavioral smoke tests for checked-in generated examples."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_checked_in_generated_examples_execute_through_real_frameworks() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_generated_examples.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "verified generated CLI command",
        "verified generated MCP tool",
        "verified dependency FastAPI route",
        "verified semantic schema example",
    ]


def test_semantic_schema_example_prints_strict_json() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "semantic_schema.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["name"] == "schema-example"
    assert payload["source_type"] == "python"
    assert [tool["name"] for tool in payload["tools"]] == ["greet"]
