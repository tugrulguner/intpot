# intpot

[![CI](https://github.com/tugrulguner/intpot/actions/workflows/ci.yml/badge.svg)](https://github.com/tugrulguner/intpot/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/intpot)](https://pypi.org/project/intpot/)
[![Python versions](https://img.shields.io/pypi/pyversions/intpot)](https://pypi.org/project/intpot/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Universal converter between CLI (Typer), MCP (FastMCP), and API (FastAPI) interfaces.

## Features

- **6 conversion directions** — CLI↔MCP↔API, any source to any target
- **Auto-detection** — automatically identifies the source framework
- **Project scaffolding** — `intpot init` creates new CLI, MCP, or API projects
- **Jinja2 templates** — clean, readable generated code
- **Fully typed** — PEP 561 compatible with py.typed marker

## Installation

```bash
pip install intpot            # core (CLI only)
pip install intpot[mcp]       # + FastMCP support
pip install intpot[api]       # + FastAPI support
pip install intpot[all]       # everything
```

## Quick Start

```bash
# Scaffold a new project
intpot init my-server --type mcp

# Convert between formats
intpot to cli server.py    # MCP/API → Typer CLI
intpot to mcp app.py       # CLI/API → FastMCP server
intpot to api app.py       # CLI/MCP → FastAPI app
```

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/tugrulguner/intpot.git
cd intpot
uv sync --all-extras
uv run pre-commit install
```

Run the full check suite:

```bash
make check   # lint + test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## License

MIT
