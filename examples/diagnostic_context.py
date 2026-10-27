"""Inspect actionable missing-binding context (requires v0.14.0 or newer).

Run: uv run --all-extras --with httpx python examples/diagnostic_context.py
The HTTP assertion uses TestClient, not a network server. All files are temporary.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

import intpot

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
    with TemporaryDirectory(prefix="intpot-diagnostic-context-") as directory:
        root = Path(directory)
        source = root / "original.py"
        source.write_text(SOURCE)
        loaded = intpot.load(source)
        response = TestClient(loaded.app).post("/value", json={"value": 3})
        assert response.status_code == 200 and response.json() == 1
        report = loaded.assess()
        diagnostics = report["diagnostics"]
        assert len(diagnostics) == 2
        for item in diagnostics:
            assert item["tool"] == "value" and item["names"] == ["Model"]
            assert item["source_location"] == {
                "path": str(source.resolve()),
                "line": SOURCE.splitlines().index("def value(x: Model) -> int:") + 1,
                "end_line": len(SOURCE.splitlines()),
            }
            assert item["references"]
            assert "Model" in item["suggested_action"]
            for scaffold in (False, True):
                output = root / f"{item['target']}-{scaffold}" / "app.py"
                try:
                    loaded.write(output, item["target"], allow_scaffold=scaffold)
                except intpot.MissingBindingError:
                    pass
                else:
                    raise AssertionError(
                        "Missing bindings must still refuse conversion"
                    )
                assert not output.parent.exists()
        print(json.dumps(diagnostics, indent=2))


if __name__ == "__main__":
    main()
