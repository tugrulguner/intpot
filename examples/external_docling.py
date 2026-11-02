"""Reproduce the pinned Docling native workflow and Intpot's current refusal.

This is a blocked-conversion experiment, not a working HTTP/MCP example.
See external-applications/docling.md for setup and evidence boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REVISION = "07154cdc82500058ad9377bac92beed3de820458"
REPOSITORY = "https://github.com/docling-project/docling"
HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Conversion fixture</title></head>
<body><h1>Conversion fixture</h1><p>İstanbul, café and a synthetic document.</p>
<ul><li>First observation</li><li>Second observation</li></ul>
<table><thead><tr><th>Item</th><th>Count</th></tr></thead>
<tbody><tr><td>Samples</td><td>3</td></tr></tbody></table>
<p><a href="#details">Local details</a></p><h2 id="details">Details</h2>
<p>This input has no external images, stylesheets or scripts.</p></body></html>
"""


def snapshot(directory: Path) -> dict[str, Any]:
    if not directory.exists():
        return {"exists": False, "entries": {}}
    if directory.is_file():
        return {
            "exists": True,
            "sha256": hashlib.sha256(directory.read_bytes()).hexdigest(),
        }
    return {
        "exists": True,
        "entries": {
            str(path.relative_to(directory)): (
                {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                if path.is_file()
                else {"directory": True}
            )
            for path in sorted(directory.rglob("*"))
        },
    }


def run(checkout: Path, output: Path) -> dict[str, Any]:
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise ValueError(f"Expected Docling revision {REVISION}, got {revision}")
    if subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain"], text=True
    ).strip():
        raise ValueError("Use an unchanged Docling checkout")
    spec = importlib.util.find_spec("docling")
    if spec is None or spec.origin is None:
        raise RuntimeError("Install the pinned Docling package first")
    installed = Path(spec.origin).parent
    source = checkout / "docling"
    python_files = sorted(source.rglob("*.py"))
    if not python_files:
        raise RuntimeError("No Docling source files found")
    for path in python_files:
        candidate = installed / path.relative_to(source)
        if not candidate.is_file() or candidate.read_bytes() != path.read_bytes():
            raise RuntimeError(f"Installed source differs: {path.relative_to(source)}")
    license_text = (checkout / "LICENSE").read_text(encoding="utf-8")
    if "MIT" not in license_text:
        raise RuntimeError("Unexpected upstream license")
    output.mkdir(parents=True, exist_ok=False)
    fixture = output / "case.html"
    fixture.write_text(HTML, encoding="utf-8")
    report: dict[str, Any] = {
        "repository": REPOSITORY,
        "revision": revision,
        "license_sha256": hashlib.sha256(license_text.encode()).hexdigest(),
        "verified_python_files": len(python_files),
        "python": sys.version,
        "python_executable": sys.executable,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("docling-slim", "intpot", "typer", "pydantic")
        },
        "native_workflow_verified": False,
        "generated_consumers_verified": False,
        "full_application_conversion_verified": False,
        "offline_evidence": "Offline environment flags only; no network audit in this driver",
        "commands": [],
    }
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
    executable = Path(sys.executable).with_name(
        "docling.exe" if sys.platform == "win32" else "docling"
    )

    def command(name: str, argv: list[str], destination: Path) -> int:
        before = snapshot(destination)
        result = subprocess.run(
            argv,
            cwd=output,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        (output / f"{name}.stdout").write_text(result.stdout, encoding="utf-8")
        (output / f"{name}.stderr").write_text(result.stderr, encoding="utf-8")
        report["commands"].append(
            {
                "name": name,
                "argv": argv,
                "exit_code": result.returncode,
                "destination_before": before,
                "destination_after": snapshot(destination),
            }
        )
        return result.returncode

    def native(name: str, input_path: Path, destination: Path, *options: str) -> int:
        return command(
            name,
            [
                str(executable),
                "convert",
                str(input_path),
                "--from",
                "html",
                "--output",
                str(destination),
                *options,
            ],
            destination,
        )

    try:
        destination = output / "native"
        if native("native-default", fixture, destination) != 0:
            raise RuntimeError(
                "Native setup/conversion failed; inspect native-default.stderr"
            )
        markdown_path = destination / "case.md"
        baseline = markdown_path.read_bytes()
        markdown = baseline.decode("utf-8")
        for expected in (
            "Conversion fixture",
            "İstanbul",
            "café",
            "First observation",
            "Samples",
        ):
            if expected not in markdown:
                raise RuntimeError(f"Missing native document content: {expected}")
        markdown_path.write_text("SENTINEL: pre-existing destination", encoding="utf-8")
        if (
            native("native-overwrite-explicit-md", fixture, destination, "--to", "md")
            != 0
        ):
            raise RuntimeError("Native overwrite failed")
        if markdown_path.read_bytes() != baseline:
            raise RuntimeError("Default/explicit Markdown or overwrite output differs")
        report["native_workflow_verified"] = True
        for name, input_path, options in (
            ("native-missing", output / "missing.html", []),
            ("native-invalid-format", fixture, ["--to", "not-a-format"]),
        ):
            target = output / name
            if native(name, input_path, target, *options) == 0:
                raise RuntimeError(f"Native rejection unexpectedly succeeded: {name}")
            if any(path.is_file() for path in target.rglob("*")):
                raise RuntimeError(f"Rejected native input left output files: {name}")
        for target in ("api", "mcp"):
            generated = output / f"converted-{target}.py"
            intpot = executable.with_name(
                "intpot.exe" if sys.platform == "win32" else "intpot"
            )
            exit_code = command(
                f"convert-{target}",
                [
                    str(intpot),
                    "to",
                    target,
                    str(source / "cli" / "main.py"),
                    "--tool",
                    "convert",
                    "--output",
                    str(generated),
                ],
                generated,
            )
            error = (output / f"convert-{target}.stderr").read_text(encoding="utf-8")
            if exit_code == 0 or generated.exists():
                raise RuntimeError(
                    "Conversion boundary changed; qualify consumers before updating this example"
                )
            if "Collection or compound enum annotations are not supported" not in error:
                raise RuntimeError(f"Unexpected first conversion blocker: {error}")
        report["first_conversion_blocker"] = (
            "Enum collections refused during inspection; callback translation also remains unsupported"
        )
        report["expected_refusal_verified"] = True
        return report
    finally:
        (output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    print(
        json.dumps(
            run(arguments.source_checkout.resolve(), arguments.output_dir.resolve()),
            indent=2,
        )
    )
