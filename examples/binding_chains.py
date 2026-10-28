"""Explain bounded binding paths (requires v0.15.0 or newer).

Run: uv run --all-extras --with httpx python examples/binding_chains.py
Until v0.15.0 is published, run from a source checkout containing this change.
The multi-helper missing-name case is an explicitly caller-authored schema,
not a claim that source inspection recovers unresolved helper globals.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.cli import app as cli
from intpot.converter import assess_schema, project_schema
from intpot.core.models import ApplicationSchema, ParameterInfo, SourceType, ToolInfo

SOURCE = """from fastapi import FastAPI
app = FastAPI()
def leaf(x):
    return x * 7
def scale(x):
    return leaf(x)
@app.get('/calc')
def calc(x: int) -> int:
    return scale(x)
"""

REFUSAL_SOURCE = """from fastapi import FastAPI
from pydantic import BaseModel
class Model(BaseModel):
    value: int
app = FastAPI()
@app.post('/value')
def value(x: Model) -> int:
    return 1
"""


def main() -> None:
    with TemporaryDirectory(prefix="intpot-chains-") as directory:
        root = Path(directory)
        source = root / "original.py"
        source.write_text(SOURCE, encoding="utf-8")
        loaded = intpot.load(source)
        response = TestClient(loaded.app).get("/calc", params={"x": 3})
        assert response.status_code == 200 and response.json() == 21
        generated = root / "generated.py"
        loaded.write(generated, "cli")
        cli_result = subprocess.check_output(
            [sys.executable, str(generated), "3"], text=True
        )
        assert cli_result.strip() == "21"

        # Deliberately incomplete caller-authored schema; no source provenance is
        # fabricated for this fixture, and no recovery boundary is broadened.
        schema = ApplicationSchema.from_tools(
            name="incomplete",
            source_type=SourceType.API,
            tools=[
                ToolInfo(
                    "calc",
                    parameters=[ParameterInfo("x", "int")],
                    return_type="int",
                    function_body="return scale(x)",
                    support_definitions=[
                        "def leaf(x):\n    return x * MISSING",
                        "def scale(x):\n    return leaf(x)",
                    ],
                )
            ],
        )
        fixture_report = assess_schema(schema)
        assert len(fixture_report["diagnostics"]) == 2
        expected = ["calc", "_calc_impl", "scale", "leaf"]
        for item in fixture_report["diagnostics"]:
            assert item["references"][0]["dependency_chain"] == expected
            assert item["source_location"] is None
        for target in (SourceType.CLI, SourceType.MCP):
            try:
                project_schema(schema, target, allow_scaffold=True)
            except intpot.MissingBindingError:
                pass
            else:
                raise AssertionError(
                    "Explanations must not bypass missing-binding refusal"
                )

        # A real source-loading refusal separately proves public CLI/Python JSON
        # parity and refusal before writes; this is not a synthetic loader test.
        refused_source = root / "refused.py"
        refused_source.write_text(REFUSAL_SOURCE, encoding="utf-8")
        refused = intpot.load(refused_source)
        report = refused.assess()
        result = CliRunner().invoke(cli, ["inspect", str(refused_source), "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)[0]["assessment"] == report
        assert report["diagnostics"]
        assert all(
            ref["dependency_chain"]
            for item in report["diagnostics"]
            for ref in item["references"]
        )
        for target in ("cli", "mcp"):
            for scaffold in (False, True):
                output = root / f"refused-{target}-{scaffold}" / "app.py"
                try:
                    refused.write(output, target, allow_scaffold=scaffold)
                except intpot.MissingBindingError:
                    assert not output.parent.exists()
                else:
                    raise AssertionError("Expected refusal before output writes")
        print(
            json.dumps(
                {
                    "original_http_result": response.json(),
                    "generated_cli_result": int(cli_result),
                    "fixture_kind": "caller-authored incomplete schema",
                    "fixture_diagnostics": fixture_report["diagnostics"],
                    "source_diagnostics": report["diagnostics"],
                    "cli_json_parity": True,
                    "refused_before_write": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
