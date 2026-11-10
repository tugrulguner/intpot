"""Generate HTTP and MCP servers from the enum-export application."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

import intpot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    server_dir = shlex.quote(str(args.output_dir))
    source = Path(__file__).parent / "enum_export" / "app.py"
    app = intpot.load(source)
    app.write(args.output_dir / "enum_api.py", "api")
    app.write(args.output_dir / "enum_mcp.py", "mcp")
    print(
        f"Wrote {args.output_dir / 'enum_api.py'} and {args.output_dir / 'enum_mcp.py'}"
    )
    print("Run from this source checkout with Python 3.11 and all extras installed.")
    print(
        "The generated source imports the example package; launch with PYTHONPATH=examples."
    )
    print(
        f"HTTP: PYTHONPATH=examples uv run --no-sync uvicorn enum_api:app --app-dir {server_dir} --host 127.0.0.1 --port 8000"
    )
    print(
        "MCP: connect a stdio PythonStdioTransport to enum_mcp.py with PYTHONPATH=examples."
    )


if __name__ == "__main__":
    main()
