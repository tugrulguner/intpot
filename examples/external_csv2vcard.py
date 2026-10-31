"""Run a pinned, unmodified third-party CLI and report Intpot conversion blockers.

See examples/external-applications/csv2vcard.md for installation and commands.
This is a case study, not a claim that csv2vcard is fully convertible.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import intpot

REVISION = "04a99668550779603774d6d86635314421eccb56"
REPOSITORY = "https://github.com/tech4242/csv2vcard"
CONTACTS = (
    "last_name,first_name,email,phone\n"
    "Example,Ada,ada@example.com,+12025550101\n"
    "Example,Lin,lin@example.com,+12025550102\n"
)


def run(checkout: Path, output: Path) -> dict[str, Any]:
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise ValueError(f"Expected csv2vcard revision {REVISION}, got {revision}")
    if subprocess.check_output(
        ["git", "-C", str(checkout), "status", "--porcelain"], text=True
    ).strip():
        raise ValueError("Use an unmodified csv2vcard checkout")
    package = importlib.import_module("csv2vcard")
    if package.__file__ is None:
        raise ValueError("csv2vcard must be installed from the pinned checkout")
    installed_root = Path(package.__file__).parent
    source_files = sorted((checkout / "csv2vcard").rglob("*.py"))
    for source in source_files:
        relative = source.relative_to(checkout / "csv2vcard")
        if source.read_bytes() != (installed_root / relative).read_bytes():
            raise ValueError(f"Installed csv2vcard source differs: {relative}")

    output.mkdir(parents=True, exist_ok=False)
    contacts = output / "contacts.csv"
    contacts.write_text(CONTACTS, encoding="utf-8")
    workflows = []
    cases = [
        (
            "individual_v3",
            ["convert", str(contacts), "--output", str(output / "v3")],
            0,
        ),
        (
            "combined_v4",
            [
                "convert",
                str(contacts),
                "--output",
                str(output / "v4"),
                "--vcard-version",
                "4.0",
                "--single-vcard",
            ],
            0,
        ),
        ("mapping", ["mapping"], 0),
        (
            "invalid_version",
            [
                "convert",
                str(contacts),
                "--output",
                str(output / "invalid"),
                "--vcard-version",
                "9.9",
            ],
            1,
        ),
        (
            "missing_source",
            [
                "convert",
                str(output / "missing.csv"),
                "--output",
                str(output / "missing"),
            ],
            2,
        ),
    ]
    for name, arguments, expected_exit in cases:
        process = subprocess.run(
            [sys.executable, "-m", "csv2vcard.cli", *arguments],
            cwd=output,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        (output / f"{name}.stdout").write_text(process.stdout, encoding="utf-8")
        (output / f"{name}.stderr").write_text(process.stderr, encoding="utf-8")
        if process.returncode != expected_exit:
            raise RuntimeError(f"{name}: exit {process.returncode}: {process.stderr}")
        if name == "mapping" and not json.loads(process.stdout):
            raise RuntimeError("The original mapping command returned no fields")
        workflows.append({"workflow": name, "exit_code": process.returncode})

    vcards = []
    for path in sorted(output.rglob("*.vcf")):
        data = path.read_bytes()
        vcards.append(
            {
                "file": str(path.relative_to(output)),
                "cards": data.count(b"BEGIN:VCARD"),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    if len(list((output / "v3").glob("*.vcf"))) != 2:
        raise RuntimeError("Expected two individual vCard files")
    if (output / "v4" / "contacts.vcf").read_bytes().count(b"BEGIN:VCARD") != 2:
        raise RuntimeError("Expected two contacts in the combined vCard")
    if (output / "invalid").exists() or (output / "missing").exists():
        raise RuntimeError("Rejected original inputs unexpectedly created output")

    source = checkout / "csv2vcard" / "cli.py"
    application = intpot.load(source)
    conversions = {}
    for target in ("api", "mcp"):
        try:
            code = getattr(application, f"to_{target}")()
        except intpot.UnsupportedCLIParameterCallbackError as error:
            conversions[target] = {
                "status": "refused",
                "error": type(error).__name__,
                "message": str(error),
            }
        else:
            (output / f"generated_{target}.py").write_text(code, encoding="utf-8")
            conversions[target] = {"status": "generated_not_exercised"}

    report = {
        "repository": REPOSITORY,
        "revision": revision,
        "installed_source_files_verified": len(source_files),
        "fixture": "Two synthetic example.com contacts; no user contact data",
        "original_workflows": workflows,
        "original_vcards": vcards,
        "discovered_tools": [tool.name for tool in application.tools],
        "assessment": application.assess(),
        "conversions": conversions,
        "full_application_conversion_verified": False,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.source_checkout.resolve(), args.output_dir.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
