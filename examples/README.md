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
| `advanced_api.py` | FastAPI | User CRUD with `Body(...)`, `Optional`, path params, multiple HTTP methods |
| `dependency_api.py` | FastAPI | Authenticated profile route with `Depends()`; intentionally rejected by CLI/MCP conversion |

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

`dependency_api.py` deliberately exercises FastAPI `Depends()`. It remains runnable and
inspectable, but conversion to CLI or MCP is expected to fail before writing output until
[dependency mapping](https://github.com/tugrulguner/intpot/issues/20) is implemented. The
demo verifies both rejection paths while retaining the complete supported conversion set.

## Regenerating

To regenerate all conversions, verify the expected dependency rejections, and execute the
checked-in generated CLI/MCP artifacts plus the dependency FastAPI route:

```bash
bash scripts/demo.sh
```
