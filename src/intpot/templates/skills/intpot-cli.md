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
