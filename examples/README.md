# Examples

`binding_chains.py` requires an unreleased source checkout. It runs a helper-backed
original HTTP API and generated CLI, then explains an explicitly caller-authored
incomplete schema. A separate real-source refusal verifies CLI/Python report parity
and no output writes; the synthetic fixture does not expand source recovery.

`source_provenance.py` (requires v0.14.0 or newer) executes an original HTTP API
with TestClient, verifies tool/helper definition coordinates, compares Python and
CLI JSON assessments, and preserves refusal before writes. Dynamic/synthetic
metadata stays unavailable; definition bounds are not exact missing-name positions.

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

## Definition-binding diagnostics

`definition_bindings.py` exercises the eager diagnostics published in v0.11.1 and the
v0.12.0 string/postponed-annotation name check. It creates a
temporary FastAPI source with a Pydantic `Model` annotation and requests the original endpoint.
It then reports `missing_definition_binding` for MCP and `missing_annotation_binding` for CLI.
Both conversions raise `MissingBindingError` before any output directory, even with scaffold opt-in.

```bash
uv run --all-extras --with httpx python examples/definition_bindings.py
```

This checks missing global roots; it does not recover classes or certify complete annotation resolution.
The example starts no network server and removes its temporary source on exit.

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
