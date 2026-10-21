"""Inspect an eager annotation that cannot survive standalone MCP conversion.

Run: uv run --all-extras --with httpx python examples/definition_bindings.py
Requires: intpot[api] and httpx for the original HTTP consumer check.
The example creates only temporary files; it does not start a network server.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import intpot

# No future import in this source: Model is an eager annotation on Python 3.11.
# Loading and serving the original is valid, but arbitrary class recovery is not
# part of Intpot's supported conversion subset.
SOURCE = """from fastapi import FastAPI
from pydantic import BaseModel

class Model(BaseModel):
    value: int

app = FastAPI()

@app.post('/value')
def value(x: Model) -> int:
    return 1
"""


def main() -> None:
    with TemporaryDirectory(prefix="intpot-definition-example-") as directory:
        root = Path(directory)
        source = root / "source_api.py"
        source.write_text(SOURCE)
        loaded = intpot.load(source)
        response = TestClient(loaded.app).post("/value", json={"value": 3})
        assert response.status_code == 200, response.text
        assert response.json() == 1
        print("Original HTTP API: /value = 1")

        report = loaded.assess()
        assert report["body_recovery_complete"]
        diagnostics = report["diagnostics"]
        assert [
            (item["code"], item["tool"], item["target"], item["names"])
            for item in diagnostics
        ] == [("missing_definition_binding", "value", "mcp", ["Model"])]
        print("mcp: missing_definition_binding names=['Model']")

        for scaffold in (False, True):
            output = root / f"generated-{scaffold}" / "server.py"
            try:
                loaded.write(output, "mcp", allow_scaffold=scaffold)
            except intpot.MissingBindingError as exc:
                assert "Model" in str(exc), exc
            else:
                raise AssertionError(
                    "An unavailable annotation binding must be refused"
                )
            assert not output.parent.exists(), (
                "Refusal must happen before output writes"
            )
        print("MCP conversion refused before writing, including scaffold opt-in")


if __name__ == "__main__":
    main()
