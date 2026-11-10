"""Generate selected-tool HTTP and MCP servers from the slug workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

import intpot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    app = intpot.load(Path(__file__).with_name("selected_tools.py")).select("slug")
    app.write(args.output_dir / "selected_api.py", "api")
    app.write(args.output_dir / "selected_mcp.py", "mcp")
    print(
        f"Wrote {args.output_dir / 'selected_api.py'} and {args.output_dir / 'selected_mcp.py'}"
    )
    print("Run from this source checkout with Python 3.11 and all extras installed.")
    print(
        f"HTTP: uv run --no-sync uvicorn selected_api:app --app-dir {args.output_dir} --host 127.0.0.1 --port 8000"
    )
    print("MCP: connect a stdio PythonStdioTransport to selected_mcp.py.")


if __name__ == "__main__":
    main()
