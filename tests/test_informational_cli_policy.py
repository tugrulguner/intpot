from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from intpot.cli import app


@pytest.mark.parametrize("directory", [False, True])
@pytest.mark.parametrize("as_json", [False, True])
def test_inspect_cli_policy_reports_qualified_assessment(
    directory, as_json, callback_annotations_eager
):
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    target = source.parent if directory else source
    arguments = ["inspect", str(target), "--callback-policy", "exclusive-informational"]
    if as_json:
        arguments.append("--json")
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    assert "exclusive-informational" in result.output
    if as_json:
        payload = json.loads(result.output)[0]
        assessment = payload["assessment"]
        assert assessment["callback_policy"] == "exclusive-informational"
        if callback_annotations_eager:
            assert assessment["diagnostics"] == []
        else:
            assert len(assessment["diagnostics"]) == 4
            assert {item["code"] for item in assessment["diagnostics"]} == {
                "unsupported_cli_parameter_callback"
            }
            assert all(
                item["reference_analysis"] == "skipped_due_to_refusal"
                for item in assessment["diagnostics"]
            )
        assert any(
            parameter.get("unsupported_callback")
            for tool in payload["tools"]
            for parameter in tool["parameters"]
        )
    invalid = CliRunner().invoke(
        app, ["inspect", str(target), "--callback-policy", "unknown"]
    )
    assert invalid.exit_code == 1 and "Unknown callback policy" in invalid.output
    assert "Traceback" not in invalid.output


@pytest.mark.parametrize("invocation", ["runner", "process"])
def test_conversion_cli_policy_generates_executable_api(
    tmp_path, monkeypatch, invocation, eager_callback_annotations
):
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    monkeypatch.syspath_prepend(str(source.parent.parent))
    monkeypatch.setenv("PYTHONPATH", str(source.parent.parent))
    target = tmp_path / "generated_api.py"
    arguments = [
        "to",
        "api",
        str(source),
        "--callback-policy",
        "exclusive-informational",
        "-o",
        str(target),
    ]
    if invocation == "runner":
        result = CliRunner().invoke(app, arguments)
        assert result.exit_code == 0 and target.exists(), (
            result.output,
            result.exception,
        )
    else:
        process = subprocess.run(
            [sys.executable, str(Path(sys.executable).parent / "intpot"), *arguments],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert process.returncode == 0 and target.exists(), (
            process.stdout,
            process.stderr,
        )
    namespace: dict[str, Any] = {"__name__": "cli_generated_information"}
    exec(target.read_text(), namespace)
    with TestClient(namespace["app"]) as client:
        response = client.post("/convert", json={"version": True, "format": "invalid"})
        assert (
            response.status_code == 200
            and response.json()["result"] == "informational-text 1.0\n"
        )


@pytest.mark.parametrize("target", ["api", "mcp"])
@pytest.mark.parametrize(
    "options", [[], ["--allow-scaffold"], ["--callback-policy", "unknown"]]
)
def test_cli_refuses_without_valid_policy_before_output(tmp_path, target, options):
    source = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    destination = tmp_path / "not-created" / "generated.py"
    result = CliRunner().invoke(
        app, ["to", target, str(source), *options, "-o", str(destination)]
    )
    assert result.exit_code != 0 and isinstance(result.exception, SystemExit)
    assert not destination.parent.exists()
    assert "Traceback" not in result.output


def test_cli_directory_policy_is_atomic_and_dry_run_does_not_write(
    tmp_path, eager_callback_annotations
):
    package = tmp_path / ("campaign_" + uuid4().hex)
    package.mkdir()
    (package / "__init__.py").write_text("")
    example = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "informational_text"
        / "app.py"
    )
    (package / "aa_good.py").write_bytes(example.read_bytes())
    destination = tmp_path / "not-created"
    arguments = [
        "to",
        "api",
        str(package),
        "--callback-policy",
        "exclusive-informational",
        "-o",
        str(destination),
    ]
    preview = CliRunner().invoke(app, [*arguments, "--dry-run"])
    assert preview.exit_code == 0 and "Would generate" in preview.output
    assert not destination.exists()
    (package / "zz_bad.py").write_text("""import typer

def callback(value: bool):
    return value

app = typer.Typer()
@app.command()
def convert(extra: bool=typer.Option(False, callback=callback, is_eager=True)):
    typer.echo('business')
""")
    failed = CliRunner().invoke(app, [*arguments, "--allow-scaffold"])
    assert failed.exit_code != 0 and isinstance(failed.exception, SystemExit), (
        failed.output
    )
    assert not destination.exists()
    assert "extra" in failed.output and "Traceback" not in failed.output
