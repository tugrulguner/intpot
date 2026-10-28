"""Exact original identifier ranges (unreleased source checkout only).

Run: uv run --all-extras --with httpx python examples/reference_locations.py
The source API works with dynamic state; conversion still refuses that binding.
This adds explanatory locations, not recovery of the dynamic value.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.cli import app as cli

SOURCE = """from fastapi import FastAPI
from types import SimpleNamespace
settings = SimpleNamespace(factor=7)
app = FastAPI()
@app.get('/calc')
def calc(x: int) -> int:
    return x * settings.factor
"""


def main() -> None:
    with TemporaryDirectory(prefix="intpot-occurrences-") as directory:
        root = Path(directory)
        source = root / "original.py"
        source.write_text(SOURCE, encoding="utf-8")
        loaded = intpot.load(source)
        response = TestClient(loaded.app).get("/calc", params={"x": 3})
        assert response.status_code == 200 and response.json() == 21
        report = loaded.assess()
        assert len(report["diagnostics"]) == 2
        for diagnostic in report["diagnostics"]:
            assert diagnostic["code"] == "missing_binding"
            assert diagnostic["names"] == ["settings"]
            reference = diagnostic["references"][0]
            assert reference["dependency_chain"] == ["calc", "_calc_impl"]
            occurrences = reference["reference_locations"]
            assert len(occurrences) == 1
            occurrence = occurrences[0]
            assert occurrence["path"] == str(source)
            lines = SOURCE.splitlines()
            spelling = lines[occurrence["line"] - 1][
                occurrence["column"] - 1 : occurrence["end_column"] - 1
            ]
            assert spelling == "settings"
        result = CliRunner().invoke(cli, ["inspect", str(source), "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)[0]["assessment"] == report
        for target in ("cli", "mcp"):
            for scaffold in (False, True):
                output = root / f"refused-{target}-{scaffold}" / "app.py"
                try:
                    loaded.write(output, target, allow_scaffold=scaffold)
                except intpot.MissingBindingError:
                    assert not output.parent.exists()
                else:
                    raise AssertionError("Expected refusal before writes")
        # Existing definition coordinates are snapshots. New occurrence mapping
        # requires the source fingerprint to still match before giving a range.
        source.write_text(SOURCE + "# changed after capture\n", encoding="utf-8")
        changed = loaded.assess()
        assert changed["diagnostics"]
        assert all(
            ref["reference_locations"] is None
            for item in changed["diagnostics"]
            for ref in item["references"]
        )
        assert [item["source_location"] for item in changed["diagnostics"]] == [
            item["source_location"] for item in report["diagnostics"]
        ]
        print(
            json.dumps(
                {
                    "original_result": response.json(),
                    "diagnostics": report["diagnostics"],
                    "cli_json_parity": True,
                    "refused_before_write": True,
                    "unavailable_after_change": True,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
