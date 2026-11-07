from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import intpot


def test_write_policy_generates_executable_api(tmp_path, monkeypatch):
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    monkeypatch.syspath_prepend(str(source.parent.parent))
    monkeypatch.setenv("PYTHONPATH", str(source.parent.parent))
    loaded = intpot.load(source)
    target = tmp_path / "api.py"
    written = loaded.write(target, "api", callback_policy="exclusive-informational")
    assert written == target.resolve() and target.exists()
    namespace: dict[str, Any] = {"__name__": "written_information"}
    exec(target.read_text(), namespace)
    with TestClient(namespace["app"]) as client:
        response = client.post("/convert", json={"version": True, "format": "invalid"})
        assert (
            response.status_code == 200
            and response.json()["result"] == "informational-text 1.0\n"
        )
