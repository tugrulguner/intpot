"""Demonstrate body-binding diagnostics without recovering module helpers.

Run: uv run python examples/missing_binding.py
Requires: intpot[api]
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI

import intpot

app = FastAPI()
FACTOR = int("7")


def scale(value: int) -> int:
    return value * FACTOR


@app.get("/calc")
def calc(x: int) -> int:
    return scale(x)


def main() -> None:
    assert calc(3) == 21
    print("Original implementation: calc(3) = 21")
    loaded = intpot.load(Path(__file__))
    report = loaded.assess()
    assert report["body_recovery_complete"]
    assert all(item["names"] == ["scale"] for item in report["diagnostics"])
    print(json.dumps(report, indent=2))
    for target in ("cli", "mcp"):
        try:
            loaded.project(target, allow_scaffold=True)
        except intpot.MissingBindingError as exc:
            print(f"{target}: {exc}")
        else:
            raise AssertionError(
                "Missing helper must be refused, even with scaffold opt-in"
            )


if __name__ == "__main__":
    main()
