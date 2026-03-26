# intpot

<p align="center">
  <img src="intpot_image.png" alt="IntPot" width="600">
</p>

[![CI](https://github.com/tugrulguner/intpot/actions/workflows/ci.yml/badge.svg)](https://github.com/tugrulguner/intpot/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/intpot)](https://pypi.org/project/intpot/)
[![Python versions](https://img.shields.io/pypi/pyversions/intpot)](https://pypi.org/project/intpot/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Universal converter between CLI (Typer), MCP (FastMCP), and API (FastAPI) interfaces.**

intpot bridges three popular Python frameworks:

- **[Typer](https://typer.tiangolo.com/)** — CLI applications
- **[FastMCP](https://github.com/jlowin/fastmcp)** — Model Context Protocol servers
- **[FastAPI](https://fastapi.tiangolo.com/)** — REST API applications

Given a source file written in any of these frameworks, intpot detects the framework, inspects its functions/tools/endpoints, and generates equivalent code in the target framework.

## Features

- **6 conversion directions** — CLI to MCP, CLI to API, MCP to CLI, MCP to API, API to CLI, API to MCP
- **Python API** — `intpot.load()` accepts file paths or live app instances for programmatic conversion
- **Directory auto-discovery** — scan an entire directory and convert all found apps at once
- **Auto-detection** — automatically identifies the source framework by analyzing imports and patterns
- **HTTP method preservation** — API routes keep their GET/POST/PUT/DELETE methods through conversion
- **Project scaffolding** — `intpot init` creates new CLI, MCP, or API projects from templates
- **Jinja2 templates** — clean, readable generated code with proper type hints
- **Fully typed** — PEP 561 compatible with `py.typed` marker
- **AI agent skills** — `intpot add skills` installs skills/rules for Claude Code, Cursor, Windsurf, Copilot, Cline, and Codex
- **Zero config** — just point at a Python file and specify the target

## Installation

```bash
pip install intpot            # core (CLI conversions only)
pip install intpot[mcp]       # + FastMCP support
pip install intpot[api]       # + FastAPI support
pip install intpot[all]       # everything
```

## Quick Start

### Scaffold a new project

```bash
intpot init my-server --type mcp
intpot init my-app --type cli
intpot init my-api --type api
```

### Convert between frameworks

```bash
# MCP server -> Typer CLI
intpot to cli server.py

# CLI app -> FastMCP server
intpot to mcp app.py

# CLI app -> FastAPI app
intpot to api app.py

# Write output to a file
intpot to cli server.py --output cli_app.py

# Convert all apps in a directory
intpot to cli ./myproject/
intpot to mcp ./myproject/ --output ./converted/
```

### Install AI agent skills

```bash
# Auto-detect agents in your project
intpot add skills

# Target a specific agent
intpot add skills --agent claude
intpot add skills --agent cursor
intpot add skills --agent windsurf
intpot add skills --agent copilot
intpot add skills --agent cline
intpot add skills --agent codex

# Specify a project directory
intpot add skills --path ./myproject/
```

## Python API

Use intpot programmatically from Python:

```python
import intpot

# From a file
app = intpot.load("mcp_server.py")
cli_code = app.to_cli()
api_code = app.to_api()

# From a live instance
from fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str) -> str:
    return f"Hello, {name}!"

app = intpot.load(mcp)
print(app.to_cli())

# Write directly to a file
app.write("output/cli_app.py", "cli")
app.write("output/api_app.py", "api")
```

The `load()` function accepts file paths (str or Path) and live app instances (FastMCP, Typer, FastAPI). The returned `IntpotApp` object provides:

- `.to_cli()`, `.to_mcp()`, `.to_api()` — return generated code as strings
- `.write(path, target)` — generate and write to a file in one step (`target` is `"cli"`, `"mcp"`, `"api"`, or a `SourceType` enum)
- `.tools` — list of normalized `ToolInfo` objects describing all detected functions
- `.source_type` — detected framework type (`SourceType.CLI`, `SourceType.MCP`, or `SourceType.API`)

## Architecture

intpot uses a three-stage pipeline:

```
                    +-----------+
                    |  SOURCE   |
                    | (.py file)|
                    +-----+-----+
                          |
                    1. DETECT
                    (identify framework)
                          |
                    +-----v-----+
                    | SourceType|
                    | cli/mcp/api|
                    +-----+-----+
                          |
                    2. INSPECT
                    (extract functions)
                          |
                    +-----v-----+
                    | ToolInfo[] |
                    | (normalized|
                    |  schema)  |
                    +-----+-----+
                          |
                    3. GENERATE
                    (render template)
                          |
                    +-----v-----+
                    |  OUTPUT   |
                    | (.py code)|
                    +-----------+
```

1. **DETECT** — `core/detector.py` imports the source file and identifies whether it's a Typer app, FastMCP server, or FastAPI app
2. **INSPECT** — Framework-specific inspectors (`core/inspectors/`) extract function signatures, parameters, types, defaults, and docstrings into a normalized `ToolInfo` schema
3. **GENERATE** — Framework-specific generators (`core/generators/`) render the normalized schema into target code using Jinja2 templates

## Examples

### MCP server to CLI app

**Input** (`mcp_server.py`):
```python
from fastmcp import FastMCP

mcp = FastMCP("example-server")

@mcp.tool()
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name."""
    return f"{greeting}, {name}!"
```

**Command**: `intpot to cli mcp_server.py`

**Output**:
```python
import typer

app = typer.Typer()

@app.command()
def greet(
    name: str = typer.Argument(..., help=""),
    greeting: str = typer.Option('Hello', help=""),
) -> None:
    """Greet someone by name."""
    # TODO: implement
    typer.echo("greet called")
```

### CLI app to FastAPI

**Input** (`cli_app.py`):
```python
import typer

app = typer.Typer()

@app.command()
def add(
    a: int = typer.Argument(..., help="First number"),
    b: int = typer.Argument(..., help="Second number"),
) -> None:
    """Add two numbers together."""
    typer.echo(a + b)
```

**Command**: `intpot to api cli_app.py`

**Output**:
```python
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()

class AddRequest(BaseModel):
    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")

@app.post("/add")
def add(request: AddRequest) -> dict:
    """Add two numbers together."""
    # TODO: implement
    return {"result": "add called"}
```

### API app to MCP server

**Input** (`api_app.py`):
```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/greet")
def greet(name: str, greeting: str = "Hello") -> dict:
    """Greet someone by name."""
    return {"message": f"{greeting}, {name}!"}
```

**Command**: `intpot to mcp api_app.py`

**Output**:
```python
from fastmcp import FastMCP

mcp = FastMCP("generated-server")

@mcp.tool()
def greet(
    name: str,
    greeting: str = 'Hello',
) -> dict:
    """Greet someone by name."""
    # TODO: implement
    return "greet called"
```

See the [`examples/`](examples/) directory for all conversion outputs, including advanced examples with `import json`, `Body(...)`, `Depends()`, async tools, and more. Run `bash scripts/demo.sh` to regenerate them all.

## CLI Reference

### `intpot init`

Scaffold a new project from a template.

```
intpot init <name> --type <mcp|cli|api>
```

| Argument/Option | Description |
|----------------|-------------|
| `name` | Project name (creates a directory) |
| `--type`, `-t` | Project type: `mcp`, `cli`, or `api` (required) |

### `intpot to cli`

Convert an MCP or API source file to a Typer CLI app.

```
intpot to cli <source> [--output <path>]
```

### `intpot to mcp`

Convert a CLI or API source file to a FastMCP server.

```
intpot to mcp <source> [--output <path>]
```

### `intpot to api`

Convert a CLI or MCP source file to a FastAPI app.

```
intpot to api <source> [--output <path>]
```

| Argument/Option | Description |
|----------------|-------------|
| `source` | Path to a source Python file or directory |
| `--output`, `-o` | Output file/directory path (prints to stdout if omitted) |

### `intpot add skills`

Install intpot skills/rules for AI coding agents. Auto-detects which agents are
configured in the project, or specify one explicitly.

```
intpot add skills [--agent <name>] [--path <dir>]
```

| Option | Description |
|--------|-------------|
| `--agent`, `-a` | Target agent: `claude`, `cursor`, `windsurf`, `copilot`, `cline`, `codex` |
| `--path`, `-p` | Project root directory (defaults to current directory) |

**Supported agents and output locations:**

| Agent | Files created |
|-------|--------------|
| Claude Code | `.claude/skills/intpot-cli.md`, `.claude/skills/intpot-python.md` |
| Cursor | `.cursor/rules/intpot-cli.mdc`, `.cursor/rules/intpot-python.mdc` |
| Windsurf | `.windsurf/rules/intpot-cli.md`, `.windsurf/rules/intpot-python.md` |
| GitHub Copilot | `.github/copilot-instructions.md` (appended) |
| Cline | `.clinerules/intpot-cli.md`, `.clinerules/intpot-python.md` |
| OpenAI Codex | `AGENTS.md` (appended) |

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
make check   # lint + typecheck + test
```

Individual targets:

```bash
make lint        # ruff check + format check
make typecheck   # pyright
make test        # pytest
make format      # auto-format code
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for what's planned for v2 (full AST transform pipeline).

## License

MIT
