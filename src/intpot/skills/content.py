"""Skill content templates for different AI coding agents."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared skill content (plain markdown)
# ---------------------------------------------------------------------------

CLI_SKILL_BODY = """\
# intpot CLI

**intpot** converts between Typer (CLI), FastMCP (MCP), and FastAPI (API) Python apps.

## When to Use

Use intpot when you need to:
- Convert a CLI app to an MCP server or REST API
- Convert an MCP server to a CLI app or REST API
- Convert a FastAPI app to a CLI or MCP server
- Scaffold a new CLI, MCP, or API project

## Commands

### Scaffold a new project

```bash
intpot init <name> --type <mcp|cli|api>
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

# Preview without writing (dry run)
intpot to cli server.py --dry-run

# Verbose output (show detection details)
intpot to mcp app.py --verbose
```

## Options

| Option | Description |
|--------|-------------|
| `--output`, `-o` | Output file/directory path (prints to stdout if omitted) |
| `--verbose`, `-v` | Show detection details on stderr |
| `--dry-run` | Preview generated code without writing files |

## Installation

```bash
pip install intpot            # core (CLI conversions only)
pip install intpot[mcp]       # + FastMCP support
pip install intpot[api]       # + FastAPI support
pip install intpot[all]       # everything
```
"""

PYTHON_SKILL_BODY = """\
# intpot Python API

**intpot** provides a Python API for converting between Typer (CLI), FastMCP (MCP), \
and FastAPI (API) apps programmatically.

## When to Use

Use the Python API when you need to:
- Convert apps programmatically within scripts or pipelines
- Inspect app functions/tools/endpoints as normalized data
- Generate code from live app instances (not just files)
- Integrate intpot into build tools or CI/CD

## Core API

### `intpot.load(source)`

Load a file path or live app instance. Returns an `IntpotApp`.

```python
import intpot

# From a file path
app = intpot.load("mcp_server.py")

# From a live FastMCP instance
from fastmcp import FastMCP
mcp = FastMCP("my-server")

@mcp.tool()
def greet(name: str) -> str:
    return f"Hello, {name}!"

app = intpot.load(mcp)
```

### `IntpotApp` methods

```python
app = intpot.load("server.py")

# Generate code as strings
cli_code = app.to_cli()
mcp_code = app.to_mcp()
api_code = app.to_api()

# Write directly to files
app.write("output/cli_app.py", "cli")
app.write("output/api_app.py", "api")
app.write("output/mcp_server.py", "mcp")

# Inspect normalized tools
for tool in app.tools:
    print(tool.name, tool.description)
    for param in tool.parameters:
        print(f"  {param.name}: {param.annotation} = {param.default}")

# Check detected source type
print(app.source_type)  # SourceType.MCP, SourceType.CLI, or SourceType.API
```

### `intpot.inspect_app(source_type, app_instance)`

Low-level inspection — extract `ToolInfo` list from a live app instance.

```python
from intpot import inspect_app
from intpot.core.models import SourceType

tools = inspect_app(SourceType.MCP, mcp_instance)
for tool in tools:
    print(tool.name, [p.name for p in tool.parameters])
```

## Installation

```python
pip install intpot[all]  # includes fastmcp + fastapi extras
```
"""


# ---------------------------------------------------------------------------
# Agent-specific formatters
# ---------------------------------------------------------------------------


def claude_skill(title: str, body: str) -> str:
    """Format as a Claude Code skill (.md in .claude/skills/)."""
    return body


def cursor_rule(title: str, body: str, globs: str = '["*.py"]') -> str:
    """Format as a Cursor rule (.mdc in .cursor/rules/)."""
    slug = title.lower().replace(" ", "-")
    return (
        f"---\n"
        f"description: {title} — use intpot to convert between CLI, MCP, and API frameworks\n"
        f"globs: {globs}\n"
        f"alwaysApply: false\n"
        f"---\n\n"
        f"{body}"
    )


def windsurf_rule(title: str, body: str) -> str:
    """Format as a Windsurf rule (.md in .windsurf/rules/)."""
    return body


def copilot_instruction(title: str, body: str) -> str:
    """Format for GitHub Copilot (.github/copilot-instructions.md)."""
    return f"\n<!-- intpot: {title} -->\n\n{body}\n"


def cline_rule(title: str, body: str) -> str:
    """Format as a Cline rule (.md in .clinerules/)."""
    return body


def codex_instruction(title: str, body: str) -> str:
    """Format for OpenAI Codex CLI (AGENTS.md)."""
    return body
