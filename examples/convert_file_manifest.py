"""Generate HTTP and stdio MCP servers for the ordered file-manifest CLI.

Unreleased source-checkout capability. Use trusted local filesystem paths only.
"""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

import intpot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    app = intpot.load(Path(__file__).with_name("file_manifest.py"))
    app.write(args.output_dir / "manifest_api.py", "api")
    app.write(args.output_dir / "manifest_mcp.py", "mcp")
    directory = shlex.quote(str(args.output_dir))
    print(f"Wrote manifest_api.py and manifest_mcp.py in {args.output_dir}")
    print("Run from this source checkout with Python 3.11 and all extras installed.")
    print(
        f"HTTP: uv run --no-sync uvicorn manifest_api:app --app-dir {directory} --host 127.0.0.1 --port 8000"
    )
    print(
        f"MCP: uv run --no-sync python examples/call_converted_mcp.py manifest '<JSON arguments>' --server-dir {directory}"
    )
    print(
        "Required source: one or more string paths; --label values retain order and duplicates."
    )
    print(
        "Paths refer to the server filesystem. This example provides no authentication or upload sandbox."
    )


if __name__ == "__main__":
    main()
