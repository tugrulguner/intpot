"""Behavioral smoke tests for checked-in generated examples."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import intpot

ROOT = Path(__file__).parents[1]

CONVERSION_EXAMPLES = [
    ("mcp_server.py", "cli", "mcp_to_cli.py"),
    ("mcp_server.py", "api", "mcp_to_api.py"),
    ("cli_app.py", "mcp", "cli_to_mcp.py"),
    ("cli_app.py", "api", "cli_to_api.py"),
    ("api_app.py", "cli", "api_to_cli.py"),
    ("api_app.py", "mcp", "api_to_mcp.py"),
    ("advanced_cli.py", "mcp", "advanced_cli_to_mcp.py"),
    ("advanced_cli.py", "api", "advanced_cli_to_api.py"),
    ("advanced_mcp.py", "cli", "advanced_mcp_to_cli.py"),
    ("advanced_mcp.py", "api", "advanced_mcp_to_api.py"),
    ("advanced_api.py", "cli", "advanced_api_to_cli.py"),
    ("advanced_api.py", "mcp", "advanced_api_to_mcp.py"),
]


@pytest.mark.parametrize(
    ("source_name", "target", "generated_name"), CONVERSION_EXAMPLES
)
def test_checked_in_conversion_matches_current_generator(
    source_name: str,
    target: str,
    generated_name: str,
) -> None:
    loaded = intpot.load(ROOT / "examples" / source_name)
    generated = getattr(loaded, f"to_{target}")()
    checked_in = (ROOT / "examples" / "conversions" / generated_name).read_text()

    assert checked_in == generated


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
