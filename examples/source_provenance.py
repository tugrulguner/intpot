"""Exercise bounded source-definition provenance (unreleased source checkout).

Run: uv run --all-extras --with httpx python examples/source_provenance.py
The original HTTP check uses TestClient. Inspection imports trusted source.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.cli import app as cli
from intpot.converter import assess_schema
from intpot.core.models import ApplicationSchema, SourceType, ToolInfo

SOURCE = """from fastapi import FastAPI
from pydantic import BaseModel
class Model(BaseModel):
    value: int
app = FastAPI()
def scale(x: int) -> int:
    return x * 7
@app.post('/value')
def value(x: Model) -> int:
    return scale(x.value)
"""


def main() -> None:
    with TemporaryDirectory(prefix="intpot-provenance-") as directory:
        root = Path(directory)
        source = root / "original.py"
        source.write_text(SOURCE, encoding="utf-8")
        loaded = intpot.load(source)
        response = TestClient(loaded.app).post("/value", json={"value": 3})
        assert response.status_code == 200 and response.json() == 21
        metadata = loaded.schema.tools[0].to_dict()
        expected = {"path": str(source.resolve()), "line": 9, "end_line": 10}
        assert metadata["source_location"] == expected
        assert metadata["support_source_locations"] == {
            "scale": {"path": str(source.resolve()), "line": 6, "end_line": 7}
        }
        assessment = loaded.assess()
        assert assessment["diagnostics"]
        assert all(
            item["source_location"] == expected for item in assessment["diagnostics"]
        )
        result = CliRunner().invoke(cli, ["inspect", str(source), "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)[0]["assessment"] == assessment
        for scaffold in (False, True):
            output = root / f"output-{scaffold}" / "app.py"
            try:
                loaded.write(output, "cli", allow_scaffold=scaffold)
            except intpot.MissingBindingError:
                assert not output.parent.exists()
            else:
                raise AssertionError("Missing Model binding must refuse before writes")
        synthetic = ApplicationSchema.from_tools(
            name="synthetic",
            source_type=SourceType.API,
            source_path=source,
            tools=[ToolInfo("unknown", function_body="return ABSENT")],
        )
        unavailable = assess_schema(synthetic)["diagnostics"][0]["source_location"]
        assert unavailable is None  # The application path is not callable provenance.
        print(
            json.dumps(
                {
                    "original_result": response.json(),
                    "tool_location": metadata["source_location"],
                    "helper_locations": metadata["support_source_locations"],
                    "diagnostics": assessment["diagnostics"],
                    "cli_json_parity": True,
                    "refused_before_write": True,
                    "unavailable_location": unavailable,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
