# intpot

<p align="center">
  <img src="intpot_image.png" alt="IntPot" width="600">
</p>

[![CI](https://github.com/tugrulguner/intpot/actions/workflows/ci.yml/badge.svg)](https://github.com/tugrulguner/intpot/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/intpot)](https://pypi.org/project/intpot/)
[![Python versions](https://img.shields.io/pypi/pyversions/intpot)](https://pypi.org/project/intpot/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Write once, serve as CLI, API, or MCP. Plus convert between all three.**

intpot bridges three popular Python frameworks:

- **[Typer](https://typer.tiangolo.com/)** — CLI applications
- **[FastMCP](https://github.com/jlowin/fastmcp)** — Model Context Protocol servers
- **[FastAPI](https://fastapi.tiangolo.com/)** — REST API applications

Define your tools once with `@app.tool()` and serve them as any framework — or convert existing code between all three.

## Features

- **Write once, serve everywhere** — `intpot.App` lets you define tools once and serve as CLI, API, or MCP with a single command
- **6 conversion directions** — CLI to MCP, CLI to API, MCP to CLI, MCP to API, API to CLI, API to MCP
- **Eject to standalone code** — `intpot eject` exports your universal app as standalone Typer, FastAPI, or FastMCP code
- **Python API** — `intpot.load()` accepts file paths or live app instances for programmatic conversion
- **Directory auto-discovery** — scan an entire directory and convert all found apps at once
- **Auto-detection** — automatically identifies the source framework by analyzing imports and patterns
- **HTTP method preservation** — API routes keep their GET/POST/PUT/DELETE methods through conversion
- **Parameter source preservation** — FastAPI `Query`, `Header`, `Path`, and `Body` parameters stay where they were, instead of collapsing into a request body
- **Project scaffolding** — `intpot init` creates new CLI, MCP, or API projects from templates
- **Jinja2 templates** — clean, readable generated code with proper type hints
- **Fully typed** — PEP 561 compatible with `py.typed` marker
- **AI agent skills** — `intpot add skills` installs skills/rules for Claude Code, Cursor, Windsurf, Copilot, Cline, and Codex
- **Zero config** — just point at a Python file and specify the target

## Installation

```bash
pip install intpot            # core: init, inspect, add skills, and Typer CLI output
pip install intpot[mcp]       # + FastMCP support
pip install intpot[api]       # + FastAPI support
pip install intpot[all]       # everything
```

The extras are only needed for frameworks you actually touch: reading a FastMCP server
or emitting one requires `[mcp]`, and the same goes for `[api]` and FastAPI.

## Quick Start

### Write once, serve everywhere

Define your tools once, serve as CLI, API, or MCP:

```python
from intpot import App

app = App("my-app")

@app.tool()
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

@app.tool()
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name."""
    return f"{greeting}, {name}!"
```

The tool name and description default to the function name and its docstring. Override
either when the two audiences want different things — the docstring explains the code to
whoever maintains it, the description tells an agent when to call the tool:

```python
@app.tool(name="lookup", description="Look up a customer by their account number.")
def fetch_customer_record(account_id: str) -> dict:
    """Hit the accounts table. Assumes the caller already validated account_id."""
    ...
```

Then serve in any mode:

```bash
intpot serve app.py --cli          # Run as Typer CLI
intpot serve app.py --api          # Run as FastAPI on port 8000
intpot serve app.py --mcp          # Run as MCP server for AI agents
```

In CLI mode, everything after the flags belongs to your app:

```bash
$ intpot serve app.py --cli add 2 3
5
$ intpot serve app.py --cli greet World --greeting Hi
Hi, World!
```

Or eject to standalone framework code:

```bash
intpot eject app.py --to api       # Export as standalone FastAPI app
intpot eject app.py --to cli       # Export as standalone Typer CLI
intpot eject app.py --to mcp       # Export as standalone FastMCP server
```

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

### Universal App (write once, serve everywhere)

```python
from intpot import App

app = App("my-app")

@app.tool()
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone."""
    return f"{greeting}, {name}!"

# Serve as any framework
app.serve(mode="cli")                         # Run as Typer CLI
app.serve(mode="api", port=8000)              # Run as FastAPI on 127.0.0.1
app.serve(mode="mcp")                         # Run as MCP server

# Eject to standalone code
cli_code = app.eject("cli")                   # Returns Typer code string
api_code = app.eject("api")                   # Returns FastAPI code string

# Access normalized tool definitions
for tool in app.tools:
    print(tool.name, tool.parameters)
```

### Conversion API (convert existing framework code)

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

**`App`** (universal runtime):
- `.tool(name=None, description=None)` — decorator to register functions as tools; both arguments override the defaults taken from the function name and docstring
- `.serve(mode, host, port)` — serve as CLI, API, or MCP
- `.eject(target)` — generate standalone framework code
- `.tools` — list of normalized `ToolInfo` objects

**`IntpotApp`** (conversion wrapper, returned by `intpot.load()`):
- `.to_cli()`, `.to_mcp()`, `.to_api()` — return generated code as strings
- `.write(path, target)` — generate and write to a file in one step
- `.tools` — list of normalized `ToolInfo` objects
- `.source_type` — detected framework type

## Architecture

Both halves of intpot meet at one normalized schema, `ToolInfo`. Everything upstream
produces it; everything downstream consumes it.

```
   @app.tool()                        source .py file
   (intpot.App)                    (Typer / FastMCP / FastAPI)
        |                                    |
        |                              1. DETECT
        |                              2. INSPECT
        |                                    |
        +--------------> ToolInfo[] <--------+
                              |
              +---------------+---------------+
              |                               |
        build a live                    3. GENERATE
      framework instance            (render a template)
              |                               |
       serve --cli/--api/--mcp        .py output on disk
                                    (to cli/mcp/api, eject)
```

The conversion side is a three-stage pipeline:

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

The runtime side skips detection and inspection: `@app.tool()` builds `ToolInfo`
directly from the function signature, then either constructs a live framework instance
(`serve`) or hands the same schema to the same generators (`eject`).

> **Detection imports your source file.** `intpot to ...` and `intpot inspect` execute
> the module to find the app instance, so any module-level code in it runs. Point them
> at code you trust.

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


def _greet_impl(
    name: str,
    greeting: str,
) -> None:
    """Greet someone by name."""
    typer.echo(f'{greeting}, {name}!')


@app.command()
def greet(
    name: str = typer.Argument(..., help=""),
    greeting: str = typer.Option('Hello', help=""),
) -> None:
    """Greet someone by name."""
    result = _greet_impl(name, greeting)
    if result is not None:
        typer.echo(result)
```

The body lives in a separate function so the command can print what it returns —
Typer discards return values, so the generated command has to echo explicitly.

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
from fastapi import FastAPI, Body

app = FastAPI()


@app.post("/add")
def add(
    a: int = Body(..., description="First number"),
    b: int = Body(..., description="Second number"),
) -> dict:
    """Add two numbers together."""

    return {'result': a + b}
```

`typer.echo(a + b)` becomes a return, wrapped so the response matches the `dict`
annotation FastAPI validates against.

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

    return {"message": f"{greeting}, {name}!"}
```

Bodies carry over where the two frameworks agree on conventions. Where they don't —
a Typer command echoing instead of returning — the body is rewritten to match the
target. Tools whose body can't be recovered generate a `# TODO: implement` stub.

See the [`examples/`](examples/) directory for all conversion outputs, including advanced examples with `import json`, `Body(...)`, `Depends()`, async tools, and more. Run `bash scripts/demo.sh` to regenerate them all.

## CLI Reference

`intpot --version` (or `-V`) prints the installed version; `intpot <command> --help`
works for any command below.

### `intpot serve`

Serve an intpot App as CLI, API, or MCP server.

```
intpot serve <source> --cli|--api|--mcp [--host <host>] [--port <port>] [--] [args...]
```

| Argument/Option | Description |
|----------------|-------------|
| `source` | Path to a Python file containing an `intpot.App` |
| `--cli` | Serve as a Typer CLI |
| `--api` | Serve as a FastAPI app |
| `--mcp` | Serve as a FastMCP server |
| `--host` | API server host (default: `127.0.0.1` — pass `0.0.0.0` to expose it on the network) |
| `--port` | API server port (default: `8000`) |
| `args...` | Passed straight to your app in `--cli` mode: `intpot serve app.py --cli add 2 3` |

Anything intpot doesn't recognise is forwarded, so your own options work as-is. Use `--`
when your app defines a flag intpot also defines:

```bash
intpot serve app.py --cli -- greet World --port 5
```

### `intpot inspect`

Show the tools intpot extracts from a source, without generating anything. Useful for
checking what a conversion will see before you run it.

```
intpot inspect <source> [--json] [--verbose]
```

| Argument/Option | Description |
|----------------|-------------|
| `source` | Path to a source Python file or directory |
| `--json` | Emit the normalized `ToolInfo` list as JSON instead of a table |
| `--verbose`, `-v` | Print detection details to stderr |

```
$ intpot inspect mcp_server.py

Source: mcp_server.py (mcp)
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┓
┃ Name  ┃ Description            ┃ Parameters            ┃ Return Type ┃ Async ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━┩
│ greet │ Greet someone by name. │ name: str, greeting:  │ str         │ No    │
│       │                        │ str='Hello'           │             │       │
└───────┴────────────────────────┴───────────────────────┴─────────────┴───────┘
```

### `intpot eject`

Export an intpot App as standalone framework code.

```
intpot eject <source> --to <cli|mcp|api> [--output <path>]
```

| Argument/Option | Description |
|----------------|-------------|
| `source` | Path to a Python file containing an `intpot.App` |
| `--to`, `-t` | Target framework: `cli`, `mcp`, `api` (required) |
| `--output`, `-o` | Output file path (prints to stdout if omitted) |

### `intpot init`

Scaffold a new project from a template.

```
intpot init <name> --type <mcp|cli|api>
```

| Argument/Option | Description |
|----------------|-------------|
| `name` | Project name (creates a directory) |
| `--type`, `-t` | Project type: `mcp`, `cli`, or `api` (required) |

### `intpot to cli` / `to mcp` / `to api`

Convert a source file — or every app in a directory — to the target framework.

```
intpot to cli <source> [--output <path>] [--dry-run] [--verbose]
intpot to mcp <source> [--output <path>] [--dry-run] [--verbose]
intpot to api <source> [--output <path>] [--dry-run] [--verbose]
```

All three take the same arguments:

| Argument/Option | Description |
|----------------|-------------|
| `source` | Path to a source Python file or directory |
| `--output`, `-o` | Output file/directory path (prints to stdout if omitted) |
| `--dry-run` | Print what would be generated, without writing any files |
| `--verbose`, `-v` | Print detection details to stderr |

`to cli` accepts MCP or API sources, `to mcp` accepts CLI or API, `to api` accepts CLI or
MCP. A source that already matches the target is skipped.

`--dry-run` is worth reaching for the first time you point intpot at unfamiliar code,
since it shows the full output and touches nothing:

```
$ intpot to cli mcp_server.py --dry-run
# --- Would generate: mcp_server_cli.py ---
"""CLI app generated by intpot."""
...
```

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

| Agent | Detected by | Files created |
|-------|-------------|--------------|
| Claude Code | `.claude/` | `.claude/skills/intpot-cli/SKILL.md`, `.claude/skills/intpot-python/SKILL.md` |
| Cursor | `.cursor/` | `.cursor/rules/intpot-cli.mdc`, `.cursor/rules/intpot-python.mdc` |
| Windsurf | `.windsurf/` | `.windsurf/rules/intpot-cli.md`, `.windsurf/rules/intpot-python.md` |
| GitHub Copilot | `.github/copilot-instructions.md` | `.github/copilot-instructions.md` (appended) |
| Cline | `.clinerules/` | `.clinerules/intpot-cli.md`, `.clinerules/intpot-python.md` |
| OpenAI Codex | never auto-detected | `AGENTS.md` (appended) |

**Codex has to be asked for by name** — `intpot add skills --agent codex`. It reads
`AGENTS.md`, but so does nearly every other tool now, so the presence of that file says
nothing about whether you use Codex. Since installing appends to it, guessing wrong would
edit your own documentation. The same reasoning is why Copilot keys off
`.github/copilot-instructions.md` rather than `.github/`, which only means the project is
on GitHub.

Running with no `--agent` and no detected marker exits without writing anything.

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
make lint              # ruff check + format check
make typecheck         # pyright
make test              # pytest
make format            # auto-format code
make changelog-draft   # preview the next release section
make changelog         # assemble changelog.d/ into CHANGELOG.md (release only)
```

Changelog entries are written as one fragment file per PR in
[`changelog.d/`](changelog.d/) rather than by editing `CHANGELOG.md`, and CI asks every
PR for one. See [`changelog.d/README.md`](changelog.d/README.md) — it's short.

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for what's planned for v2 (full AST transform pipeline).

## License

MIT
