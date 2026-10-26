"""Exercise callback/dependency assessment and refusal before any output writes.

Run with: .venv/bin/python examples/conversion_refusals.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import intpot


def main() -> None:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
        root = Path(directory)
        callback_source = root / "callback_source.py"
        callback_source.write_text("""import typer
app = typer.Typer(add_completion=False)
def validate(value):
    if value == "bad": raise typer.BadParameter("rejected")
    return value
@app.command()
def greet(name: str = typer.Option("world", callback=validate)):
    typer.echo(f"Hello {name}")
""")
        callback_app = intpot.load(callback_source)
        accepted = CliRunner().invoke(callback_app.app, ["--name", "world"])
        assert accepted.exit_code == 0, accepted.output
        assert "Hello world" in accepted.stdout
        rejected = CliRunner().invoke(callback_app.app, ["--name", "bad"])
        assert rejected.exit_code != 0
        assert "rejected" in rejected.output
        callback_report = callback_app.assess()
        print("callback assessment:", json.dumps(callback_report, sort_keys=True))
        _refuse_without_output(callback_app, "api", root / "callback-output")

        dependency_source = root / "dependency_source.py"
        dependency_source.write_text("""from fastapi import FastAPI, Depends
app = FastAPI()
def token(): return "source-token"
@app.get("/value", name="value_route")
def value(auth: str = Depends(token)):
    return {"auth": auth}
""")
        dependency_app = intpot.load(dependency_source)
        assert TestClient(dependency_app.app).get("/value").json() == {
            "auth": "source-token"
        }
        dependency_report = dependency_app.assess()
        print("dependency assessment:", json.dumps(dependency_report, sort_keys=True))
        _refuse_without_output(dependency_app, "cli", root / "dependency-output")
        print("both conversions refused before output")


def _refuse_without_output(app: intpot.IntpotApp, target: str, output: Path) -> None:
    try:
        app.write(output, target, allow_scaffold=True)
    except (
        intpot.UnsupportedCLIParameterCallbackError,
        intpot.UnsupportedFastAPIDependencyError,
    ):
        assert not output.exists()
        return
    raise AssertionError(f"{target} conversion should have been refused")


if __name__ == "__main__":
    main()
