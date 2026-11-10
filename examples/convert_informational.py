"""Generate informational-policy HTTP and MCP servers from the native example."""

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
    source = Path(__file__).parent / "informational_text" / "app.py"
    app = intpot.load(source)
    # Conversion must qualify the callbacks before this script creates its output dir.
    api = app.write(
        args.output_dir / "informational_api.py",
        "api",
        callback_policy="exclusive-informational",
    )
    mcp = app.write(
        args.output_dir / "informational_mcp.py",
        "mcp",
        callback_policy="exclusive-informational",
    )
    print(f"Wrote {api} and {mcp}")
    print("Run from this source checkout with Python 3.11 and all extras installed.")
    print(
        f"HTTP: PYTHONPATH=examples uv run --no-sync uvicorn informational_api:app --app-dir {server_dir} --host 127.0.0.1 --port 8000"
    )
    print("MCP: connect a stdio PythonStdioTransport to informational_mcp.py.")


if __name__ == "__main__":
    main()
