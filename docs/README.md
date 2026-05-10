# intpot System Design Notes

This document is a system-oriented map of the intpot project: what it is trying
to do, how the main pieces fit together, and what each important folder or file
is responsible for.

## Project Purpose

intpot is a Python code-generation and runtime bridge for three interface
styles:

- Typer command-line applications
- FastAPI HTTP APIs
- FastMCP Model Context Protocol servers

The core idea is to describe callable tools once, normalize them into an
internal schema, and then generate or serve them through one of the supported
frameworks.

There are two primary user flows:

1. Convert an existing framework app into another framework.
2. Define tools with `intpot.App` and serve or eject them as CLI, API, or MCP.

## High-Level Architecture

The conversion system follows a three-stage pipeline:

```text
Python source file or live app instance
        |
        v
Detect source framework
        |
        v
Inspect framework-specific objects
        |
        v
Normalize into ToolInfo objects
        |
        v
Transform framework conventions
        |
        v
Generate target framework source code
```

The normalized model is the center of the design. Framework-specific code is
kept at the edges:

- Detectors know how to identify a source framework.
- Inspectors know how to extract tools from one framework.
- Transforms know how to adapt behavior between frameworks.
- Generators know how to render one framework.

This keeps most of the project from needing to understand Typer, FastAPI, and
FastMCP at the same time.

## Normalized Data Model

The central schema lives in `src/intpot/core/models.py`.

`SourceType` identifies the supported framework families:

- `cli`
- `api`
- `mcp`

`ParameterInfo` represents a callable parameter:

- name
- type annotation as text
- default value, or a sentinel for required parameters
- description/help text

`ToolInfo` represents a normalized tool, command, or endpoint:

- tool name
- description
- parameters
- return type
- HTTP method and route path for FastAPI
- extracted function body
- async flag
- dependency comments
- source imports needed by the generated code

Names are sanitized through `sanitize_identifier()` so generated Python code is
valid even when source names contain dashes, spaces, keywords, or other unsafe
characters.

## Conversion Path

### Detection

`src/intpot/core/detector.py` detects source apps from either files or live
instances.

For files, it first parses the source with AST and looks for app constructors
such as `Typer()`, `FastAPI()`, or `FastMCP()`. This avoids importing obviously
irrelevant files during directory scans.

If the AST precheck passes, the file is imported with a path-hashed module name
to avoid collisions between same-named files. The detector then scans public
module attributes for known framework instance types.

### Inspection

Inspectors live in `src/intpot/core/inspectors/`.

Each inspector converts framework internals into `ToolInfo`:

- `cli.py` extracts Click/Typer commands and parameters.
- `api.py` extracts FastAPI routes, methods, path params, body metadata, and
  dependency-injected parameters.
- `mcp.py` extracts FastMCP tools from the local provider.
- `_utils.py` contains shared helpers for type names, function body extraction,
  and import extraction.
- `base.py` defines the inspector interface.

The inspectors also attempt to preserve useful source details such as docstrings,
async status, imported modules used by function bodies, and original function
bodies.

### Transforming

`src/intpot/core/transforms.py` adapts framework-specific behavior before code
generation.

The main behavioral conversion is the I/O boundary:

- CLI to API/MCP: `typer.echo(value)` becomes `return value`.
- API/MCP to CLI: `return value` becomes `typer.echo(value)`.
- `raise typer.Exit(0)` becomes `return None`.
- non-zero `typer.Exit` becomes a `RuntimeError`.

Return types are also adjusted by target framework:

- CLI outputs through `typer.echo()`, so generated CLI functions return `None`.
- FastAPI output is currently normalized to `dict`.
- MCP preserves source return types except when converting from CLI, where it
  uses `str`.

The transform layer is intentionally narrower than a full compiler. The roadmap
notes that a future version may add deeper AST-based body rewrites.

### Generation

Generators live in `src/intpot/core/generators/`.

The generator classes are intentionally thin:

- `cli.py` renders `templates/cli_app.py.j2`.
- `api.py` renders `templates/api_app.py.j2`.
- `mcp.py` renders `templates/mcp_server.py.j2`.
- `_render.py` owns shared Jinja setup, typing import discovery, extra import
  collection, docstring escaping, and naming filters.
- `base.py` defines the generator interface.

Templates live in `src/intpot/templates/` and produce standalone Python files.
If a function body cannot be recovered, generated code includes a small
`# TODO: implement` placeholder.

## Runtime Path

The runtime path is separate from converting existing framework apps.

`src/intpot/runtime.py` defines `App`, a small universal app abstraction:

```python
from intpot import App

app = App("my-app")

@app.tool()
def greet(name: str) -> str:
    return f"Hello, {name}"
```

When a function is registered, intpot inspects its signature and docstring and
builds a `ToolInfo`. The original callable is kept alongside the metadata as a
`RegisteredTool`.

`App` can:

- expose `.tools`
- serve as CLI, API, or MCP with `.serve(...)`
- generate standalone framework source with `.eject(...)`

`src/intpot/runtime_builders.py` builds live framework instances from registered
tools:

- `build_typer_app()` wraps functions so return values are printed.
- `build_fastapi_app()` registers handlers on a FastAPI app.
- `build_fastmcp_app()` registers tools on a FastMCP server.

## Public Python API

`src/intpot/converter.py` exposes the programmatic conversion API.

`intpot.load(source)` accepts:

- a file path
- a Typer app instance
- a FastAPI app instance
- a FastMCP app instance

It returns an `IntpotApp`, which provides:

- `.tools`
- `.to_cli()`
- `.to_api()`
- `.to_mcp()`
- `.write(path, target)`

The package-level exports are in `src/intpot/__init__.py`.

## CLI Design

The command-line entry point is `src/intpot/cli.py`.

It defines a Typer app with these major commands:

- `intpot init`
- `intpot inspect`
- `intpot serve`
- `intpot eject`
- `intpot to cli`
- `intpot to api`
- `intpot to mcp`
- `intpot add skills`

Command handlers live in `src/intpot/commands/`.

Important command files:

- `_convert.py` contains shared conversion logic for all `intpot to ...`
  commands.
- `to_cli.py`, `to_api.py`, and `to_mcp.py` are small wrappers around the shared
  converter.
- `inspect.py` prints extracted tools without generating code.
- `serve.py` finds an `intpot.App` in a source file and serves it.
- `eject.py` finds an `intpot.App` and writes generated standalone code.
- `init.py` scaffolds basic CLI/API/MCP projects from templates.
- `add_skills.py` installs intpot instructions for coding agents.

## Directory and File Map

### Repository Root

`README.md`

Main user-facing documentation. It explains installation, quick start, CLI
commands, Python API, and the detect-inspect-generate architecture.

`pyproject.toml`

Package metadata, dependencies, optional extras, script entry point, pytest
configuration, Pyright configuration, and Ruff settings.

`uv.lock`

Locked dependency graph for development with uv.

`Makefile`

Developer commands:

- `make install`
- `make test`
- `make lint`
- `make format`
- `make typecheck`
- `make check`
- `make build`
- `make clean`

`CHANGELOG.md`

Version history. It shows the project evolved from basic conversion, to Python
API and directory discovery, to agent skills, to the `intpot.App` runtime.

`ROADMAP.md`

Future direction. Current roadmap items include FastAPI `Annotated` support,
Typer sub-app support, better parameter description preservation, and richer AST
transforms.

`CONTRIBUTING.md`

Development setup, style, type checking, tests, and an overview of the project
structure.

`LICENSE`

MIT license.

### `src/intpot/`

Main package source.

`__init__.py`

Defines package version and exports `App`, `IntpotApp`, `inspect_app`, and
`load`.

`cli.py`

Top-level Typer CLI registration.

`converter.py`

Programmatic conversion API and `IntpotApp` wrapper.

`runtime.py`

Universal app runtime and `@app.tool()` registration.

`runtime_builders.py`

Builds live Typer, FastAPI, and FastMCP apps from registered runtime tools.

`py.typed`

Marks the package as typed for PEP 561 consumers.

### `src/intpot/core/`

Framework-independent conversion core.

`models.py`

Shared data model and identifier sanitization.

`detector.py`

Source detection for files and live app instances.

`discovery.py`

Recursive directory scanning for convertible Python apps.

`transforms.py`

AST-based body and return type adaptation between frameworks.

### `src/intpot/core/inspectors/`

Framework-specific extraction into normalized tools.

`api.py`

FastAPI route inspection.

`cli.py`

Typer/Click command inspection.

`mcp.py`

FastMCP tool inspection.

`_utils.py`

Shared source extraction and type helper functions.

`base.py`

Inspector interface.

### `src/intpot/core/generators/`

Target framework code generation.

`api.py`

FastAPI generator.

`cli.py`

Typer generator.

`mcp.py`

FastMCP generator.

`_render.py`

Shared Jinja rendering logic.

`base.py`

Generator interface.

### `src/intpot/commands/`

CLI command implementations.

`_convert.py`

Shared conversion implementation for `intpot to ...`.

`to_cli.py`, `to_api.py`, `to_mcp.py`

Target-specific wrappers.

`inspect.py`

Displays normalized tools as a table or JSON.

`serve.py`

Serves `intpot.App` files as CLI/API/MCP.

`eject.py`

Exports an `intpot.App` as standalone framework code.

`init.py`

Creates scaffold projects from templates.

`add_skills.py`

Installs intpot instructions into supported AI coding agent config locations.

### `src/intpot/templates/`

Jinja templates and scaffold files.

`cli_app.py.j2`

Standalone Typer output template.

`api_app.py.j2`

Standalone FastAPI output template.

`mcp_server.py.j2`

Standalone FastMCP output template.

`scaffold/`

Starter source files for new CLI/API/MCP projects created by `intpot init`.

`skills/`

Markdown instruction templates used by `intpot add skills`.

### `src/intpot/skills/`

Skill content loading and agent-specific formatting.

`content.py`

Reads skill templates and formats them for Claude, Cursor, Windsurf, Copilot,
Cline, and Codex.

### `tests/`

Automated tests.

Major coverage areas:

- conversion API
- detectors
- discovery
- inspectors
- generators
- command behavior
- runtime app registration
- runtime builders
- roundtrip conversion behavior
- adversarial naming, docstring, async, and route cases
- agent skill installation

`conftest.py`

Shared pytest fixture for writing temporary source files.

### `examples/`

Example source apps and generated conversion outputs.

Basic examples:

- `cli_app.py`
- `api_app.py`
- `mcp_server.py`

Advanced examples:

- `advanced_cli.py`
- `advanced_api.py`
- `advanced_mcp.py`

Runtime example:

- `universal_app.py`

`examples/conversions/`

Generated outputs for basic and advanced conversions in all supported
directions.

`examples/README.md`

Explains the examples and how to regenerate conversions.

### `docs/`

Project documentation.

`cookbook.md`

Practical conversion patterns, limitations, and gotchas.

`README.md`

This system design overview.

### `scripts/`

Utility scripts.

`demo.sh`

Regenerates example conversions and demonstrates common commands.

## Design Strengths

- The normalized `ToolInfo` model gives the project a clean center.
- Framework-specific behavior is isolated in inspectors and generators.
- The command layer is thin and mostly delegates to reusable APIs.
- Directory discovery uses AST screening before importing files.
- Generated code is template-based, which keeps output readable.
- The runtime `App` path reuses the same metadata model as conversion.
- Tests cover both direct units and end-to-end command behavior.

## Design Tradeoffs and Current Limits

- Source files are imported during detection, so source modules with import-time
  side effects can still run.
- Function body transforms are intentionally limited and do not yet model all
  framework-specific behavior.
- FastAPI dependency injection has no direct equivalent in Typer or MCP, so it
  is stripped from signatures and preserved as a comment.
- Generated API return types are simplified to `dict`.
- Round trips preserve useful behavior and signatures, but not exact original
  code structure.
- Some advanced framework features, such as FastAPI `Annotated` parameters and
  nested Typer apps, are documented as future work.

## How to Read the Codebase

For conversion behavior, start with:

1. `src/intpot/core/models.py`
2. `src/intpot/core/detector.py`
3. `src/intpot/core/inspectors/`
4. `src/intpot/core/transforms.py`
5. `src/intpot/core/generators/`
6. `src/intpot/templates/`

For runtime behavior, start with:

1. `src/intpot/runtime.py`
2. `src/intpot/runtime_builders.py`
3. `src/intpot/commands/serve.py`
4. `src/intpot/commands/eject.py`

For CLI behavior, start with:

1. `src/intpot/cli.py`
2. `src/intpot/commands/_convert.py`
3. the command file for the feature being changed

