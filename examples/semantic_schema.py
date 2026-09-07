"""Inspect the immutable schema shared by intpot's live and generated interfaces."""

from __future__ import annotations

import json

from intpot import App

app = App("schema-example")


@app.tool()
def greet(name: str, excited: bool = False) -> str:
    """Greet someone by name."""
    message = f"Hello, {name}"
    return f"{message}!" if excited else message


def main() -> None:
    """Print the canonical application schema as strict JSON."""
    print(json.dumps(app.schema.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
