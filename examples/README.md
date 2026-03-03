# Examples

This directory contains example source files and their generated conversions.

## Source Files

| File | Framework | Description |
|------|-----------|-------------|
| `cli_app.py` | Typer CLI | Two commands: `add` and `greet` |
| `mcp_server.py` | FastMCP | Two tools: `add` and `greet` |
| `api_app.py` | FastAPI | Two endpoints: `/add` and `/greet` |

## Generated Conversions

The `conversions/` directory contains the output of all 6 conversion directions, generated from the source files above.

| Output File | Command | Source |
|-------------|---------|--------|
| `conversions/cli_to_mcp.py` | `intpot to mcp examples/cli_app.py` | CLI -> MCP |
| `conversions/cli_to_api.py` | `intpot to api examples/cli_app.py` | CLI -> API |
| `conversions/mcp_to_cli.py` | `intpot to cli examples/mcp_server.py` | MCP -> CLI |
| `conversions/mcp_to_api.py` | `intpot to api examples/mcp_server.py` | MCP -> API |
| `conversions/api_to_cli.py` | `intpot to cli examples/api_app.py` | API -> CLI |
| `conversions/api_to_mcp.py` | `intpot to mcp examples/api_app.py` | API -> MCP |

## Regenerating

To regenerate all conversions:

```bash
intpot to mcp examples/cli_app.py > examples/conversions/cli_to_mcp.py
intpot to api examples/cli_app.py > examples/conversions/cli_to_api.py
intpot to cli examples/mcp_server.py > examples/conversions/mcp_to_cli.py
intpot to api examples/mcp_server.py > examples/conversions/mcp_to_api.py
intpot to cli examples/api_app.py > examples/conversions/api_to_cli.py
intpot to mcp examples/api_app.py > examples/conversions/api_to_mcp.py
```
