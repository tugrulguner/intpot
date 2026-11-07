from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot
from intpot.core.callbacks import UnsupportedCLIParameterCallbackError


@contextmanager
def _http_client(namespace, code, path, live):
    if not live:
        with TestClient(namespace["app"]) as client:
            yield client
        return
    import os
    import socket
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request
    from types import SimpleNamespace

    class NetworkClient:
        def request(self, route, data=None):
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}" + route,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            try:
                response = urllib.request.urlopen(request, timeout=15)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                text = response.read().decode()
                return SimpleNamespace(
                    status_code=response.status,
                    text=text,
                    json=lambda: json.loads(text),
                )

        def get(self, route):
            return self.request(route)

        def post(self, route, **kwargs):
            return self.request(route, json.dumps(kwargs["json"]).encode())

    target = path.parent / "generated_api.py"
    target.write_text(code)
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
    with (path.parent / "http-server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                path.parent.name + ".generated_api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=dict(os.environ),
            stdout=log,
            stderr=log,
        )
        try:
            client = NetworkClient()
            deadline = time.monotonic() + 15
            while True:
                try:
                    if client.get("/openapi.json").status_code == 200:
                        break
                except urllib.error.URLError:
                    pass
                if process.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError("Generated HTTP server failed readiness")
                time.sleep(0.05)
            yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            assert process.poll() is not None


@pytest.mark.parametrize("live", [False, True])
def test_exclusive_information_http_preserves_body_and_early_exit(
    tmp_source, monkeypatch, live
):
    path = tmp_source("""import json
from pathlib import Path
import typer
from .types import Mode
from .callbacks import version_callback, logo_callback
app=typer.Typer()
@app.command()
def convert(output: str, mode: Mode = typer.Option(Mode.MD), version: bool = typer.Option(False, callback=version_callback, is_eager=True), logo: bool = typer.Option(False, callback=logo_callback, is_eager=True)):
    Path(output).write_text(json.dumps({"mode": mode.value, "version": version, "logo": logo}))
    typer.echo("converted")
""")
    (path.parent / "__init__.py").write_text("")
    (path.parent / "types.py").write_text(
        'from enum import StrEnum\nclass Mode(StrEnum):\n    MD="md"\n    JSON="json"\n'
    )
    marker = path.parent / "callback-marker.txt"
    (path.parent / "callbacks.py").write_text(
        """from __future__ import annotations
from pathlib import Path
import typer
MARKER = """
        + repr(str(marker))
        + """
def version_callback(value: bool):
    if value:
        Path(MARKER).write_text("version")
        print("VERSION")
        raise typer.Exit()
def logo_callback(value: bool):
    if value:
        Path(MARKER).write_text("logo")
        print("LOGO")
        raise typer.Exit()
"""
    )
    # Original package remains a dependency, including in a fresh request worker.
    import os

    monkeypatch.syspath_prepend(str(path.parent.parent))
    monkeypatch.setenv(
        "PYTHONPATH",
        str(path.parent.parent) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    )
    loaded = intpot.load(path)
    native = CliRunner().invoke(loaded.app, ["--mode", "invalid", "--version"])
    assert native.exit_code == 0 and "VERSION" in native.output
    marker.unlink()
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        loaded.to_api()
    with pytest.raises(ValueError, match="Unknown callback policy"):
        loaded.to_api(callback_policy="unknown")
    with pytest.raises(UnsupportedCLIParameterCallbackError):
        loaded.to_api(allow_scaffold=True)
    code = loaded.to_api(callback_policy="exclusive-informational")
    assert not marker.exists(), "generation must not call callbacks"
    namespace: dict[str, Any] = {"__name__": "generated_info_api"}
    exec(code, namespace)
    output = path.parent / "result.json"
    with _http_client(namespace, code, path, live) as client:
        normal = client.post("/convert", json={"output": str(output), "mode": "md"})
        assert normal.status_code == 200, normal.text
        assert json.loads(output.read_text()) == {
            "mode": "md",
            "version": None,
            "logo": None,
        }
        output.unlink()
        info = client.post("/convert", json={"version": True, "mode": "invalid"})
        assert info.status_code == 200 and info.json() == {"result": "VERSION\n"}, (
            info.text
        )
        assert marker.read_text() == "version" and not output.exists()
        marker.unlink()
        conflict = client.post("/convert", json={"version": True, "logo": True})
        assert (
            conflict.status_code == 422 and not marker.exists() and not output.exists()
        )
        invalid = client.post(
            "/convert", json={"output": str(output), "mode": "invalid"}
        )
        assert (
            invalid.status_code == 422 and not output.exists() and not marker.exists()
        )
    assert all(
        p.unsupported_callback
        for p in loaded.schema.tools[0].parameters
        if p.informational_callback
    )
