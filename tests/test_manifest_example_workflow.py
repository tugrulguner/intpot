from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent


def test_manifest_example_retains_file_order_duplicates_and_labels(
    tmp_path: Path,
) -> None:
    source = ROOT / "examples/file_manifest.py"
    assert source.is_file(), "The feature needs a runnable manifest source example"
    spec = importlib.util.spec_from_file_location("manifest_example_workflow", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        first = tmp_path / "first.txt"
        second = tmp_path / "second file.txt"
        first.write_bytes(b"alpha\n")
        second.write_bytes(b"beta\n")
        destination = tmp_path / "manifest.json"
        paths = [str(first), str(second), str(first)]
        result = CliRunner().invoke(
            module.app,
            [
                *paths,
                "--output",
                str(destination),
                "--label",
                "release",
                "--label",
                "A B",
                "--label",
                "release",
            ],
        )
        assert result.exit_code == 0, (result.output, result.exception)
        record = json.loads(destination.read_text())
        assert record["count"] == 3
        assert record["labels"] == ["release", "A B", "release"]
        assert record["files"] == [
            {
                "path": name,
                "bytes": len(Path(name).read_bytes()),
                "sha256": hashlib.sha256(Path(name).read_bytes()).hexdigest(),
            }
            for name in paths
        ]
        absent = tmp_path / "must-not-write.json"
        invalid = CliRunner().invoke(module.app, ["--output", str(absent)])
        assert invalid.exit_code != 0
        assert not absent.exists()
    finally:
        sys.modules.pop(spec.name, None)


def test_manifest_recipe_runs_native_http_and_stdio_mcp(tmp_path: Path) -> None:
    generated = tmp_path / "generated servers"
    recipe = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/convert_file_manifest.py"),
            "--output-dir",
            str(generated),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert recipe.returncode == 0, recipe.stderr
    first = tmp_path / "first.txt"
    second = tmp_path / "second file.txt"
    first.write_bytes(b"alpha\n")
    second.write_bytes(b"beta\n")
    sources = [str(first), str(second), str(first)]
    labels = ["release", "A B", "release"]
    native_output = tmp_path / "native.json"
    native = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/file_manifest.py"),
            *sources,
            "--output",
            str(native_output),
            "--label",
            labels[0],
            "--label",
            labels[1],
            "--label",
            labels[2],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert native.returncode == 0, native.stderr
    expected = json.loads(native_output.read_text())
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "manifest_api:app",
            "--app-dir",
            str(generated),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            assert proc.poll() is None, proc.communicate()
            try:
                httpx.get(
                    f"http://127.0.0.1:{port}/openapi.json", timeout=1
                ).raise_for_status()
                break
            except httpx.ConnectError:
                assert time.monotonic() < deadline
                time.sleep(0.05)
        output = tmp_path / "http.json"
        response = httpx.post(
            f"http://127.0.0.1:{port}/manifest",
            json={"source": sources, "label": labels, "output": str(output)},
        )
        assert response.status_code == 200, response.text
        assert json.loads(output.read_text()) == expected
        rejected = tmp_path / "http-rejected.json"
        response = httpx.post(
            f"http://127.0.0.1:{port}/manifest",
            json={"source": [], "output": str(rejected)},
        )
        assert response.status_code == 422 and not rejected.exists()
    finally:
        proc.terminate()
        try:
            proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=2)
    output = tmp_path / "mcp.json"
    client = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/call_converted_mcp.py"),
            "manifest",
            json.dumps({"source": sources, "label": labels, "output": str(output)}),
            "--server-dir",
            str(generated),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert client.returncode == 0, client.stderr
    assert "Manifest written for 3 inputs" in client.stdout
    assert json.loads(output.read_text()) == expected
