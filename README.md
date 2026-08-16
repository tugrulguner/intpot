# intpot

<p align="center">
  <img src="intpot_image.webp" alt="intpot: Python tools served as CLI, API, or MCP" width="520">
</p>

<p align="center">
  <strong>One Python tool definition. A Typer CLI, FastAPI app, or FastMCP server.</strong>
</p>

<p align="center">
  Use it live, eject standalone framework code, or convert an existing app in any of six directions.
</p>

<p align="center">
  <a href="https://pypi.org/project/intpot/"><img src="https://img.shields.io/pypi/v/intpot" alt="PyPI version"></a>
  <a href="https://pypi.org/project/intpot/"><img src="https://img.shields.io/pypi/pyversions/intpot" alt="Python versions"></a>
  <a href="https://github.com/tugrulguner/intpot/actions/workflows/ci.yml"><img src="https://github.com/tugrulguner/intpot/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/tugrulguner/intpot/stargazers"><img src="https://img.shields.io/github/stars/tugrulguner/intpot?style=flat" alt="GitHub stars"></a>
  <a href="https://github.com/tugrulguner/intpot/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#convert-an-existing-app">Convert an app</a> ·
  <a href="#what-conversion-preserves">Conversion scope</a> ·
  <a href="#cli-reference">CLI reference</a> ·
  <a href="#contributing">Contributing</a>
</p>

## Why intpot

A useful Python function often needs three interfaces: a command for people, an HTTP
endpoint for applications, and an MCP tool for AI agents. Maintaining three copies means
three signatures, three sets of descriptions, and three places for behavior to drift.

intpot gives you two ways out:

| Starting point | What intpot does |
|---|---|
| Plain Python functions | Register them once with `@app.tool()`, then serve or eject CLI, API, and MCP interfaces |
| An existing Typer, FastAPI, or FastMCP app | Inspect it, normalize its tools, and generate either of the other two frameworks |

The output is ordinary Python. Ejected and converted apps do not depend on intpot.

## Quick start

Install every runtime for the complete experience:

```bash
pip install "intpot[all]"
```

### Write once, serve everywhere

Save this as `app.py`:

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

With API mode running, call the same names as POST routes with JSON request bodies:

```bash
$ curl -s -X POST http://127.0.0.1:8000/add \
    -H "Content-Type: application/json" \
    -d '{"a": 2, "b": 3}'
5
```

MCP mode exposes `add` and `greet` as FastMCP tools with schemas derived from their type
annotations and defaults.

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

Install only the frameworks you need if you do not want the full extra:

```bash
pip install intpot          # Core commands and Typer output
pip install "intpot[mcp]"   # Add FastMCP support
pip install "intpot[api]"   # Add FastAPI support
```

## Convert an existing app

intpot detects Typer, FastAPI, and FastMCP apps from a Python file and supports every
conversion between them:

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

Use `intpot inspect app.py` first when you want to see the normalized tool definitions
before generating code. Converted output is readable Python that you can review, test,
and change.

## Give your coding agent intpot context

Install project-local instructions for Claude Code, Cursor, Windsurf, GitHub Copilot,
Cline, or OpenAI Codex:

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

## What intpot handles

- **One definition, three live interfaces:** serve an `intpot.App` through Typer,
  FastAPI, or FastMCP.
- **Six conversion directions:** move existing apps between all three frameworks.
- **Standalone output:** eject or convert to normal framework code with no intpot runtime
  dependency.
- **Behavior-aware transforms:** preserve function bodies and imports, and translate
  framework conventions such as `typer.echo()` into return values.
- **Interface fidelity:** carry types, defaults, and async functions through supported
  conversions, and apply FastAPI parameter sources when generating an API.
- **Programmatic access:** use `intpot.load()` and normalized `ToolInfo` objects from
  Python.
- **Project tooling:** scan directories, scaffold projects, and install agent guidance
  for six coding agents.

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
- `.tool(name=None, description=None)` — decorator to register functions as tools; both arguments override the defaults taken from the function name and docstring. Functions with `*args` or `**kwargs` are rejected because those parameters have no consistent CLI, HTTP API, and MCP representation.
- `.serve(mode, host, port)` — serve as CLI, API, or MCP
- `.eject(target)` — generate standalone framework code
- `.tools` — list of normalized `ToolInfo` objects

**`IntpotApp`** (conversion wrapper, returned by `intpot.load()`):
- `.to_cli()`, `.to_mcp()`, `.to_api()` — return generated code as strings
- `.write(path, target)` — generate and write to a file in one step
- `.tools` — list of normalized `ToolInfo` objects
- `.source_type` — detected framework type

## What conversion preserves

intpot is designed to produce code you can own, rather than hide conversion behind a
runtime adapter. Its normalized `ToolInfo` schema carries the parts that the three
frameworks share:

- tool names, descriptions, types, defaults, and async behavior;
- recoverable function bodies and the direct imports they reference;
- framework metadata that has a target equivalent, including supported `Query`, `Header`,
  `Path`, and `Body` parameter sources when generating FastAPI;
- scalar returns translated into a shape the target framework can serve correctly.

Frameworks do not have one-to-one equivalents for every feature. Review generated code
when a source uses nested Typer command groups, `Annotated[..., Body(...)]`, FastAPI
`Depends()`, Pydantic model parameters, streaming, background tasks, or framework-specific
error handling. Transitive imports, external services, and configuration are not
provisioned for you. If intpot cannot recover a body, it emits a `# TODO: implement` stub
instead of inventing behavior.

> [!IMPORTANT]
> Detection imports the source module, so only inspect or convert code you trust. intpot
> is alpha software: compile the generated file, import it with its dependencies, and
> exercise a real CLI command, API request, or MCP tool before shipping it.

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

Conversion follows three stages: detect the framework, inspect its tools into
`ToolInfo[]`, then render the target framework. The runtime side starts at the same schema:
`@app.tool()` creates `ToolInfo` directly, then `serve` builds a live framework instance
or `eject` sends it through the generators.

## Conversion examples

The repository includes checked-in source and generated output for every direction:

| Source | Typer target | FastAPI target | FastMCP target |
|---|---|---|---|
| Typer | — | [`cli_to_api.py`](examples/conversions/cli_to_api.py) | [`cli_to_mcp.py`](examples/conversions/cli_to_mcp.py) |
| FastAPI | [`api_to_cli.py`](examples/conversions/api_to_cli.py) | — | [`api_to_mcp.py`](examples/conversions/api_to_mcp.py) |
| FastMCP | [`mcp_to_cli.py`](examples/conversions/mcp_to_cli.py) | [`mcp_to_api.py`](examples/conversions/mcp_to_api.py) | — |

[`examples/`](examples/) also contains advanced inputs and outputs with direct imports,
async tools, request bodies, `Depends()`, path parameters, and multiple HTTP methods.
Run `bash scripts/demo.sh` to regenerate all twelve conversions locally.

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
| `--output`, `-o` | Output file path (prints to stdout if omitted). Missing parent directories are created |

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
| `--output`, `-o` | Output file/directory path (prints to stdout if omitted). Missing directories are created |
| `--dry-run` | Print what would be generated, without writing any files |
| `--verbose`, `-v` | Print detection details to stderr |

`to cli` accepts MCP or API sources, `to mcp` accepts CLI or API, `to api` accepts CLI or
MCP. A source that already matches the target is skipped.

`--dry-run` shows generated output without writing generated files, but it is not a
sandbox: detection still imports the source and executes arbitrary module-level code.
Only point intpot at source you trust:

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
| GitHub Copilot | `.github/copilot-instructions.md` | `.github/copilot-instructions.md` (managed block) |
| Cline | `.clinerules/` | `.clinerules/intpot-cli.md`, `.clinerules/intpot-python.md` |
| OpenAI Codex | never auto-detected | `AGENTS.md` (managed block) |

**Codex has to be asked for by name** — `intpot add skills --agent codex`. It reads
`AGENTS.md`, but so does nearly every other tool now, so the presence of that file says
nothing about whether you use Codex. Since installing appends to it, guessing wrong would
edit your own documentation. The same reasoning is why Copilot keys off
`.github/copilot-instructions.md` rather than `.github/`, which only means the project is
on GitHub.

Running with no `--agent` and no detected marker exits without writing anything.
Copilot and Codex installations use bounded intpot-managed blocks, so rerunning the
command updates or repairs intpot guidance while preserving surrounding project content.
For Codex, intpot warns when the resulting `AGENTS.md` exceeds Codex's default 32 KiB
instruction limit.

## Contributing

intpot has a small core with clear extension points: inspectors turn frameworks into
`ToolInfo`, generators turn `ToolInfo` into source, and runtime builders expose live
interfaces. Contributions can improve conversion fidelity, add real-world examples,
strengthen generated-code tests, or make the developer experience clearer.

- Start with a [good first issue](https://github.com/tugrulguner/intpot/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
- Browse work where [help is wanted](https://github.com/tugrulguner/intpot/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22).
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for the pull request process and
  [`docs/reviewing.md`](docs/reviewing.md) for the contracts changes must preserve.

### Development setup

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

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the current polish backlog and the planned full AST
transform pipeline.

## Support intpot

If intpot removes a duplicate interface from your project, consider
[starring the repository](https://github.com/tugrulguner/intpot). Stars help other Python
developers find the project, while issues and pull requests make it better.

## License

MIT
