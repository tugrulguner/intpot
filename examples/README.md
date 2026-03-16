# Examples

This directory contains example source files and their generated conversions.

## Source Files

### Basic

| File | Framework | Description |
|------|-----------|-------------|
| `cli_app.py` | Typer CLI | Two commands: `add` and `greet` |
| `mcp_server.py` | FastMCP | Two tools: `add` and `greet` |
| `api_app.py` | FastAPI | Two endpoints: `/add` and `/greet` |

### Advanced

| File | Framework | Description |
|------|-----------|-------------|
| `advanced_cli.py` | Typer CLI | Task manager with `json`, multiple commands, booleans |
| `advanced_mcp.py` | FastMCP | Notes server with `hashlib`, `datetime`, `json`, async tools |
| `advanced_api.py` | FastAPI | User CRUD with `Body(...)`, `Depends()`, `Optional`, path params, multiple HTTP methods |

## Generated Conversions

The `conversions/` directory contains all conversion outputs — 6 basic + 6 advanced.

### Basic

| Output File | Command |
|-------------|---------|
| `conversions/cli_to_mcp.py` | `intpot to mcp examples/cli_app.py` |
| `conversions/cli_to_api.py` | `intpot to api examples/cli_app.py` |
| `conversions/mcp_to_cli.py` | `intpot to cli examples/mcp_server.py` |
| `conversions/mcp_to_api.py` | `intpot to api examples/mcp_server.py` |
| `conversions/api_to_cli.py` | `intpot to cli examples/api_app.py` |
| `conversions/api_to_mcp.py` | `intpot to mcp examples/api_app.py` |

### Advanced

| Output File | Command |
|-------------|---------|
| `conversions/advanced_cli_to_mcp.py` | `intpot to mcp examples/advanced_cli.py` |
| `conversions/advanced_cli_to_api.py` | `intpot to api examples/advanced_cli.py` |
| `conversions/advanced_mcp_to_cli.py` | `intpot to cli examples/advanced_mcp.py` |
| `conversions/advanced_mcp_to_api.py` | `intpot to api examples/advanced_mcp.py` |
| `conversions/advanced_api_to_cli.py` | `intpot to cli examples/advanced_api.py` |
| `conversions/advanced_api_to_mcp.py` | `intpot to mcp examples/advanced_api.py` |

## Regenerating

To regenerate all conversions:

```bash
bash scripts/demo.sh
```
